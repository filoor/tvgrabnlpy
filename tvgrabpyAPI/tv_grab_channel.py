#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Python 3 compatibility
from __future__ import unicode_literals
# from __future__ import print_function

import codecs, locale, os, io, shutil, smtplib

import re, sys, traceback, difflib
import time, datetime, pytz, random
from threading import Thread, Lock, RLock, Event
from Queue import Queue, Empty
from xml.sax import saxutils
from copy import copy, deepcopy

class Channel_Config(Thread):
    """
    Class that holds the Channel definitions and manages the data retrieval and processing
    """
    def __init__(self, config, chanid = 0, name = '', group = 99):
        Thread.__init__(self)
        # Flag to stop the thread
        self.config = config
        self.functions = self.config.fetch_func
        self.channel_node = None
        self.quit = False
        self.state = None
        self.statetext = ''
        self.thread_type = 'channel'

        # Flags to indicate the data is in
        self.source_data = {}
        self.detail_data = Event()
        self.child_data = Event()
        self.cache_return = Queue()
        self.channel_lock = Lock()

        # Flag to indicate all data is processed
        self.ready = False

        self.active = False
        self.is_child = False
        self.child_programs = []
        self.counter = 0
        self.chanid = chanid
        self.xmltvid = self.chanid
        self.chan_name = name
        self.group = group
        self.source_id = {}
        self.icon_source = -1
        self.icon = ''

        # This will contain the final fetcheddata
        self.all_programs = []
        self.current_prime = ''

        self.opt_dict = {}
        self.prevalidate_opt = {}
        self.opt_dict['xmltvid_alias'] = None
        self.opt_dict['disable_source'] = []
        self.opt_dict['disable_detail_source'] = []
        self.opt_dict['disable_ttvdb'] = False
        self.opt_dict['prime_source'] = -1
        self.prevalidate_opt['prime_source'] = -1
        self.opt_dict['prefered_description'] = -1
        self.opt_dict['append_tvgidstv'] = True
        self.opt_dict['fast'] = self.config.opt_dict['fast']
        self.opt_dict['slowdays'] = self.config.opt_dict['slowdays']
        self.opt_dict['compat'] = self.config.opt_dict['compat']
        self.opt_dict['legacy_xmltvids'] = self.config.opt_dict['legacy_xmltvids']
        self.opt_dict['max_overlap'] = self.config.opt_dict['max_overlap']
        self.opt_dict['overlap_strategy'] = self.config.opt_dict['overlap_strategy']
        self.opt_dict['logos'] = self.config.opt_dict['logos']
        self.opt_dict['desc_length'] = self.config.opt_dict['desc_length']
        self.opt_dict['use_split_episodes'] = self.config.opt_dict['use_split_episodes']
        self.opt_dict['cattrans'] = self.config.opt_dict['cattrans']
        self.opt_dict['mark_hd'] = self.config.opt_dict['mark_hd']
        self.opt_dict['add_hd_id'] = False
        self.config.threads.append(self)

    def validate_settings(self):

        if not self.active and not self.is_child:
            return

        if self.prevalidate_opt['prime_source'] == -1:
            self.config.validate_option('prime_source', self)

        else:
            self.config.validate_option('prime_source', self, self.prevalidate_opt['prime_source'])

        self.config.validate_option('prefered_description', self)
        self.config.validate_option('overlap_strategy', self)
        self.config.validate_option('max_overlap', self)
        self.config.validate_option('desc_length', self)
        self.config.validate_option('slowdays', self)
        if self.group in self.config.ttvdb_disabled_groups:
            self.opt_dict['disable_ttvdb'] = True

        if self.opt_dict['xmltvid_alias'] != None:
            self.xmltvid = self.opt_dict['xmltvid_alias']

        elif (self.config.configversion < 2.208 or self.opt_dict['legacy_xmltvids'] == True):
            xmltvid = self.chanid.split('-',1)
            self.xmltvid = xmltvid[1] if int(xmltvid[0]) < 4 else self.chanid

    def run(self):

        if not self.active and not self.is_child:
            self.ready = True
            self.state = None
            for index in self.config.source_order:
                self.source_ready(index).set()

            self.detail_data.set()
            return

        if not self.is_child:
            self.state = None
            self.child_data.set()

        try:
            # Create the merge order
            self.statetext = 'preparing'
            self.state = 1
            self.merge_order = []
            last_merge = []
            if (self.get_source_id(self.opt_dict['prime_source']) != '') \
              and not (self.opt_dict['prime_source'] in self.opt_dict['disable_source']) \
              and not (self.opt_dict['prime_source'] in self.config.opt_dict['disable_source']):
                if self.get_source_id(self.opt_dict['prime_source']) in self.config.channelsource[self.opt_dict['prime_source']].no_genric_matching:
                    last_merge.append(self.opt_dict['prime_source'])

                else:
                    self.merge_order.append(self.opt_dict['prime_source'])

            for index in self.config.source_order:
                if (self.get_source_id(index) != '') \
                  and index != self.opt_dict['prime_source'] \
                  and not (index in self.opt_dict['disable_source']) \
                  and not (index in self.config.opt_dict['disable_source']):
                    if self.get_source_id(index) in self.config.channelsource[index].no_genric_matching:
                        last_merge.append(index)

                    else:
                        self.merge_order.append(index)

                elif index != self.opt_dict['prime_source']:
                    self.source_ready(index).set()

            self.merge_order.extend(last_merge)
            # Retrieve and merge the data from the available sources.
            self.statetext = 'waiting for basepages'
            self.state = 2
            for index in self.merge_order:
                while not self.source_ready(index).is_set():
                    # Wait till the event is set by the source, but check every 5 seconds for an unexpected break or wether the source is still alive
                    self.source_ready(index).wait(5)
                    if self.quit:
                        self.ready = True
                        return

                    # Check if the source is still alive
                    if not self.config.channelsource[index].is_alive():
                        self.source_ready(index).set()
                        break

                if self.source_ready(index).is_set():
                    if len(self.config.channelsource[index].program_data[self.chanid]) == 0:
                        # Nothing was returned. We log unless it is a virtual source
                        if not self.config.channelsource[index].is_virtual:
                            self.config.log(self.config.text('fetch', 51, (self.config.channelsource[index].source, self.chan_name)))

                    elif self.channel_node == None:
                        # This is the first source with data, so we just take in the data creating the channel Node
                        with self.config.channelsource[index].source_lock:
                            self.channel_node = ChannelNode(self.config, self, self.config.channelsource[index].program_data[self.chanid][:], index)

                    else:
                        # There is already data, so we merge the incomming data into that
                        with self.config.channelsource[index].source_lock:
                            self.channel_node.merge_source(self.config.channelsource[index].program_data[self.chanid][:], index)

            if self.chanid in self.config.combined_channels.keys():
                self.statetext = 'waiting for children'
                self.state = 3
                for c in self.config.combined_channels[self.chanid][:]:
                    if c['chanid'] in self.config.channels:
                        while not self.config.channels[c['chanid']].child_data.is_set():
                            # Wait till the event is set by the child, but check every 5 seconds for an unexpected break or wether the child is still alive
                            self.config.channels[c['chanid']].child_data.wait(5)
                            if self.quit:
                                self.ready = True
                                return

                            # Check if the child is still alive
                            if not self.config.channels[c['chanid']].is_alive():
                                break

                        if not isinstance(self.config.channels[c['chanid']].channel_node, ChannelNode) \
                          or self.config.channels[c['chanid']].channel_node.program_count() == 0:
                            self.config.log(self.config.text('fetch', 51, (self.config.channels[c['chanid']].chan_name, self.chan_name)))

                        elif self.child_data.is_set():
                            if self.channel_node == None:
                                self.channel_node = ChannelNode(self.config, self)

                            self.channel_node.merge_channel(self.config.channels[c['chanid']].channel_node)

            if self.is_child and not self.active:
                self.child_data.set()
                self.statetext = ''
                self.state = None
                #~ self.ready = True

            # And get the detailpages
            #~ elif not isinstance(self.channel_node, ChannelNode) or self.channel_node.program_count() == 0:
            elif len(self.all_programs) == 0:
                self.statetext = ''
                self.state = None
                self.detail_data.set()

            else:
                self.statetext = 'processing details'
                #~ print 'processing details for ', self.chanid
                self.state = 4
                self.get_details()
                self.statetext = 'waiting for details'
                self.state = 5
                while not self.detail_data.is_set():
                    #~ print 'waiting for details for ', self.chanid
                    self.detail_data.wait(5)
                    if self.quit:
                        self.ready = True
                        return

                    # Check if the sources are still alive
                    s_cnt = 0
                    for s in self.config.detail_sources:
                        s_cnt += 1
                        if self.config.channelsource[s].is_alive():
                            break

                        if s_cnt == 1:
                            log_string = self.config.channelsource[s].source

                        elif s_cnt == len(self.config.detail_sources):
                            log_string += u' and %s' % self.config.channelsource[s].source

                        else:
                            log_string += u', %s' % self.config.channelsource[s].source

                    else:
                        self.detail_data.set()
                        self.config.log([self.config.text('fetch', 52, (log_string, )), self.config.text('fetch', 53, (self.chan_name,))])

                self.all_programs = self.detailed_programs

            if self.is_child:
                #~ print 'setting active child_data for', self.chanid
                self.child_data.set()

            # And log the results
            with self.functions.count_lock:
                self.functions.progress_counter+= 1
                counter = self.functions.progress_counter

            log_array = ['\n', self.config.text('fetch', 54, (self.chan_name, counter, self.config.chan_count))]
            log_array.append( self.config.text('fetch',55, (self.functions.get_counter('detail', -1, self.chanid), )))
            if self.opt_dict['fast']:
                log_array.append(self.config.text('fetch', 56, (self.functions.get_counter('fail', -1, self.chanid), )))
                log_array.append('\n')
                log_array.append(self.config.text('fetch', 57, (self.functions.get_counter('detail', -2, self.chanid), )))
                log_array.append(self.config.text('fetch', 58, (self.functions.get_counter('fail', -2, self.chanid), )))

            else:
                fail = 0
                for source in self.config.detail_sources:
                    fail += self.functions.get_counter('fail', source, self.chanid)
                    log_array.append(self.config.text('fetch', 59, \
                        (self.functions.get_counter('detail', source, self.chanid), self.config.channelsource[source].source)))

                log_array.append(self.config.text('fetch', 60, (fail,)))
                log_array.append(self.config.text('fetch', 61, (self.functions.get_counter('fail', -1, self.chanid), )))
                log_array.append('\n')
                log_array.append(self.config.text('fetch', 57, (self.functions.get_counter('lookup', -2, self.chanid), )))
                log_array.append(self.config.text('fetch', 58, (self.functions.get_counter('lookup_fail', -2, self.chanid), )))
                log_array.append('\n')
                for source in self.config.detail_sources:
                    log_array.append(self.config.text('fetch', 62, \
                        (self.config.channelsource[source].detail_request.qsize(), self.config.channelsource[source].source)))

            log_array.append('\n')
            self.config.log(log_array, 4, 3)

            # a final check on the sanity of the data
            self.channel_node.check_lineup()
            # Split titles with colon in it
            # Note: this only takes place if all days retrieved are also grabbed with details (slowdays=days)
            # otherwise this function might change some titles after a few grabs and thus may result in
            # loss of programmed recordings for these programs.
            # Also check if a genric genre does aply
            for g, chlist in self.config.generic_channel_genres.items():
                if self.chanid in chlist:
                    gen_genre = g
                    break

            else:
                gen_genre = None

            for i, v in enumerate(self.all_programs):
                self.all_programs[i] = self.title_split(v)
                if gen_genre != None and self.all_programs[i]['genre'] in (u'overige', u''):
                    self.all_programs[i]['genre'] = gen_genre

            if self.opt_dict['add_hd_id']:
                self.opt_dict['mark_hd'] = False
                self.config.xml_output.create_channel_strings(self.chanid, False)
                self.config.xml_output.create_program_string(self.chanid, False)
                self.config.xml_output.create_channel_strings(self.chanid, True)
                self.config.xml_output.create_program_string(self.chanid, True)

            else:
                self.config.xml_output.create_channel_strings(self.chanid)
                self.config.xml_output.create_program_string(self.chanid)

            if self.config.write_info_files:
                self.config.infofiles.write_raw_list()

            self.statetext = ''
            self.state = None
            self.ready = True

        except:
            self.config.logging.log_queue.put({'fatal': [traceback.format_exc(), '\n'], 'name': self.chan_name})
            self.ready = True
            return(97)

    def use_cache(self, tdict, cached):
        # copy the cached information, except the start/end times, rating and clumping,
        # these may have changed.
        # But first checkout the dict
        #~ try:
            #~ clump  = tdict['clumpidx']

        #~ except LookupError:
            #~ clump = False

        cached['start-time'] = tdict['start-time']
        cached['stop-time']  = tdict['stop-time']
        #~ if clump:
            #~ cached['clumpidx'] = clump

        # Make sure we do not overwrite fresh info with cashed info
        if tdict['description'] > cached['description']:
            cached['description'] = tdict['description']

        if not 'prefered description' in cached.keys():
            cached['prefered description'] = tdict['prefered description']

        elif tdict['prefered description'] > cached['prefered description']:
            cached['prefered description'] = tdict['prefered description']

        for fld in ('name', 'episode title', 'originaltitle', 'premiere year', 'airdate', 'country', 'star-rating', 'broadcaster'):
            if tdict[fld] != '':
                cached[fld] = tdict[fld]

        if re.sub('[-,. ]', '', cached['name']) == re.sub('[-,. ]', '', cached['episode title']):
            cached['episode title'] = ''

        for fld in ('season', 'episode'):
            if tdict[fld] != 0:
                cached[fld] = int(tdict[fld])

        if tdict['rerun'] == True:
            cached['rerun'] = True

        if len(tdict['rating']) > 0:
            for item in tdict['rating']:
                if not item in cached['rating']:
                    cached['rating'].append(item)

        return cached

    def get_counter(self):
        with self.channel_lock:
            self.fetch_counter += 1
            return 100*float(self.fetch_counter)/float(self.nprograms)

    def get_source_id(self, source):
        if source in self.source_id.keys():
            return self.source_id[source]

        return ''

    def source_ready(self, source):
        if not source in self.source_data.keys():
            self.source_data[source] = Event()

        return self.source_data[source]

    def get_details(self, ):
        """
        Given a list of programs, from the several sources, retrieve program details
        """
        # Check if there is data
        self.detailed_programs = []
        if len(self.all_programs) == 0:
            return

        programs = self.all_programs[:]

        if self.opt_dict['fast']:
            self.config.log(['\n', self.config.text('fetch', 63, \
                (len(programs), self.chan_name, self.xmltvid, (self.opt_dict['compat'] and self.config.compat_text or ''))), \
                self.config.text('fetch', 64, (self.counter, self.config.chan_count, self.config.opt_dict['days']))], 2)

        else:
            self.config.log(['\n', self.config.text('fetch', 65, \
                (len(programs), self.chan_name, self.xmltvid, (self.opt_dict['compat'] and self.config.compat_text or ''))), \
                self.config.text('fetch', 64, (self.counter, self.config.chan_count, self.config.opt_dict['days']))], 2)

        # randomize detail requests
        self.fetch_counter = 0
        self.nprograms = len(programs)
        fetch_order = list(range(0,self.nprograms))
        random.shuffle(fetch_order)

        for i in fetch_order:
            if self.quit:
                self.ready = True
                return

            try:
                if programs[i] == None:
                    continue

            except:
                self.config.log(traceback.format_exc())
                if self.config.write_info_files:
                    self.config.infofiles.write_raw_string('Error: %s with index %s\n' % (sys.exc_info()[1], i))

                continue

            p = programs[i]
            logstring = u'%s-%s: %s' % \
                                (p['start-time'].strftime('%d %b %H:%M'), \
                                p['stop-time'].strftime('%H:%M'), \
                                p['name'])

            # We only fetch when we are in slow mode and slowdays is not set to tight
            no_fetch = (self.opt_dict['fast'] or p['offset'] >= (self.config.opt_dict['offset'] + self.opt_dict['slowdays']))
            no_fetch = True

            # check the cache for this program's ID
            # If not found, check the various ID's and (if found) make it the prime one
            self.config.program_cache.cache_request.put({'task':'query_id', 'parent': self, 'program': p})
            cache_id = self.cache_return.get(True)
            if cache_id =='quit':
                self.ready = True
                return

            if cache_id != None:
                self.config.program_cache.cache_request.put({'task':'query', 'parent': self, 'pid': cache_id})
                cached_program = self.cache_return.get(True)
                if cached_program =='quit':
                    self.ready = True
                    return

                # check if it contains detail info from tvgids.nl or (if no nl-url known, or in no_fetch mode) tvgids.tv
                if cached_program != None and \
                    (no_fetch or \
                        cached_program[self.config.channelsource[0].detail_check] or \
                        (p['detail_url'][0] == '' and \
                            (cached_program[self.config.channelsource[9].detail_check] or \
                                (p['detail_url'][9] == '' and \
                                cached_program[self.config.channelsource[1].detail_check])))):
                        self.config.log(self.config.text('fetch', 18, (self.chan_name, self.get_counter(), logstring)), 8, 1)
                        self.functions.update_counter('detail', -1, self.chanid)
                        p = self.use_cache(p, cached_program)
                        if not (self.config.opt_dict['disable_ttvdb'] or self.opt_dict['disable_ttvdb']):
                            if p['genre'].lower() == u'serie/soap' and p['episode title'] != '' and p['season'] == 0:
                                #~ self.update_counter('fetch', -1)
                                self.functions.update_counter('queue', -2, self.chanid)
                                self.config.ttvdb.detail_request.put({'tdict':p, 'parent': self, 'task': 'update_ep_info'})
                                continue

                        self.detailed_programs.append(p)
                        continue

            # Either we are fast-mode, outside slowdays or there is no url. So we continue
            no_detail_fetch = (no_fetch or ((p['detail_url'][0] == '') and \
                                                                (p['detail_url'][9] == '') and \
                                                                (p['detail_url'][1] == '')))

            if no_detail_fetch:
                self.config.log(self.config.text('fetch', 66, (self.chan_name, self.get_counter(), logstring)), 8, 1)
                self.functions.update_counter('fail', -1, self.chanid)
                if not (self.config.opt_dict['disable_ttvdb'] or self.opt_dict['disable_ttvdb']):
                    if p['genre'].lower() == u'serie/soap' and p['episode title'] != '' and p['season'] == 0:
                        #~ self.update_counter('fetch', -1)
                        self.functions.update_counter('queue', -2, self.chanid)
                        self.config.ttvdb.detail_request.put({'tdict':p, 'parent': self, 'task': 'update_ep_info'})
                        continue

                self.detailed_programs.append(p)

                continue

            for src_id in self.config.detail_sources:
                if src_id not in self.config.opt_dict['disable_detail_source'] and \
                  src_id not in self.opt_dict['disable_detail_source'] and \
                  p['detail_url'][src_id] != '':
                    #~ self.update_counter('fetch', src_id)
                    self.functions.update_counter('queue',src_id, self.chanid)
                    self.config.channelsource[src_id].detail_request.put({'tdict':p, 'cache_id': cache_id, 'logstring': logstring, 'parent': self})
                    break

        # Place terminator items in the queue
        for src_id in self.config.detail_sources:
            if self.functions.get_counter('queue', src_id, self.chanid) > 0:
                self.config.channelsource[src_id].detail_request.put({'last_one': True, 'parent': self})
                break

        else:
            if not (self.config.opt_dict['disable_ttvdb'] or self.opt_dict['disable_ttvdb']):
                self.config.ttvdb.detail_request.put({'task': 'last_one', 'parent': self})

            else:
                self.detail_data.set()

    def title_split(self,program):
        """
        Some channels have the annoying habit of adding the subtitle to the title of a program.
        This function attempts to fix this, by splitting the name at a ': '.
        """
        # Some programs (BBC3 when this happened) have no genre. If none, then set to a default
        if program['genre'] is None:
            program['genre'] = 'overige';

        ptitle = program['name']
        psubtitle = program['episode title']
        if  ptitle == None or ptitle == '':
            return program

        # exclude certain programs
        if  ('episode title' in program and psubtitle != '')  \
          or ('genre' in program and program['genre'].lower() in ['movies','film']) \
          or (ptitle.lower() in self.config.notitlesplit):
            return program

        # and do the title split test
        p = ptitle.split(':')
        if len(p) >1:
            self.config.log(self.config.text('fetch', 67, (ptitle, )), 64)
            program['name'] = p[0].strip()
            program['episode title'] = "".join(p[1:]).strip()
            if self.config.write_info_files:
                self.config.infofiles.addto_detail_list(unicode('Name split = %s + %s' % (program['name'] , program['episode title'])))

        return program

# end Channel_Config

class ChannelNode():
    def __init__(self, config, channel_config, programs = None, source = None):
        self.node_lock = RLock()
        with self.node_lock:
            self.prime_source = None
            self.adding_from = ''
            self.config = config
            self.tz = self.config.output_tz
            self.channel_config = channel_config
            self.chanid = channel_config.chanid
            self.max_overlap = datetime.timedelta(minutes = self.channel_config.opt_dict['max_overlap'])
            self.name = channel_config.chan_name
            self.shortname = self.name[:15] if len(self.name) > 15 else self.name
            self.current_stats = {}
            self.adding_stats = {}
            self.merge_stats = {}
            if not self.chanid in self.config.channels.keys():
                return

            if not self.chanid in self.config.channelprogram_rename.keys():
                self.config.channelprogram_rename[self.chanid] = {}

            self.key_list = []
            for kl in self.config.key_values.values():
                self.key_list.extend(kl)

            self.key_list.extend(['genre', 'title','genres'])
            self.config.key_values['source'] = ['prog_ID', 'detail_url', 'detail_fetched']
            self.config.key_values['dict'] = ['credits', 'video']
            self.clear_all_programs()
            self.checkrange = [0]
            for i in range(1, 30):
                self.checkrange.extend([i, -i])

            self.child_times = []
            self.groupslot_names = self.config.groupslot_names[:]
            if self.chanid in self.config.combined_channels.keys():
                # This channel has children
                date_now = self.config.in_fetch_tz(datetime.datetime.now(pytz.utc)).toordinal()
                start_date = date_now + self.config.opt_dict['offset']
                start_time = self.config.fetch_func.merge_date_time(start_date, datetime.time(0, 0), self.config.combined_channels_tz)
                end_date = start_date + self.config.opt_dict['days']
                end_time = self.config.fetch_func.merge_date_time(end_date, datetime.time(0, 0), self.config.combined_channels_tz)
                clist = self.config.combined_channels[self.chanid]
                if 'start' in clist[0]:
                    # They have time restrictions
                    clist.sort(key=lambda ctime: (ctime['start']))
                    if clist[-1]['start'] > clist[-1]['end']:
                        cend = self.config.fetch_func.merge_date_time(start_date, clist[-1]['end'], self.config.combined_channels_tz)
                        cstart = self.config.fetch_func.merge_date_time(start_date - 1, clist[-1]['start'], self.config.combined_channels_tz)
                        last_date = {'real-start': cstart, 'start': start_time, 'stop': cend, 'chanid': clist[-1]['chanid'], 'slots': []}
                        if 'slots' in clist[-1]:
                            last_date['slots'] = clist[-1]['slots']

                    else:
                        last_date = {'start': start_time, 'stop': None, 'chanid': None, 'slots': []}

                    for offset in range(start_date, end_date):
                        for item in clist:
                            cstart = self.config.fetch_func.merge_date_time(offset, item['start'], self.config.combined_channels_tz)
                            if item['end'] > item['start']:
                                cend = self.config.fetch_func.merge_date_time(offset, item['end'], self.config.combined_channels_tz)
                            else:
                                cend = self.config.fetch_func.merge_date_time(offset + 1, item['end'], self.config.combined_channels_tz)

                            if last_date['stop'] == None or last_date['chanid'] == None or last_date['stop'] > cstart:
                                last_date['stop'] = cstart

                            self.child_times.append(last_date)
                            if last_date['stop'] < cstart:
                                self.child_times.append({'start': last_date['stop'], 'stop': cstart, 'chanid': None, 'slots': []})

                            last_date = {'start': cstart, 'stop': cend, 'chanid': item['chanid'], 'slots': []}
                            if 'slots' in item:
                                last_date['slots'] = item['slots']

                    if last_date['stop'] > end_time:
                        last_date['real-stop'] = last_date['stop']
                        last_date['stop'] = end_time

                    self.child_times.append(last_date)

                for child in self.config.combined_channels[self.chanid]:
                    if 'slots' in child.keys():
                        if isinstance(child['slots'], (str, unicode)):
                            self.groupslot_names.append(re.sub('[-,. ]', '', self.config.fetch_func.remove_accents(child['slots']).lower().strip()))

                        elif isinstance(child['slots'], list):
                            for gs in child['slots']:
                                if isinstance(gs, (str, unicode)):
                                    self.groupslot_names.append(re.sub('[-,. ]', '', self.config.fetch_func.remove_accents(gs).lower().strip()))

            self.merge_type = None
            if source in self.config.channelsource.keys():
                self.prime_source = source
                self.merge_source(programs, source)

    def clear_all_programs(self):
        with self.node_lock:
            self.programs = []
            self.program_gaps = []
            self.group_slots = []
            self.programs_by_start = {}
            self.programs_by_stop = {}
            self.programs_by_name = {}
            self.programs_by_matchname = {}
            self.programs_with_no_genre = {}
            self.start = None
            self.stop = None
            self.first_node = None
            self.last_node = None
            self.current_list = []
            self.adding_list = []

    def save_current_stats(self):
        with self.node_lock:
            self.current_list = self.programs[:]
            self.current_stats['start'] = copy(self.start)
            self.current_stats['stop'] = copy(self.stop)
            self.current_stats['count'] = self.program_count()
            self.current_stats['groups'] = len(self.group_slots)
            self.current_stats['start-str'] = '            '
            if isinstance(self.current_stats['start'], datetime.datetime):
                self.current_stats['start-str'] = self.config.in_output_tz(self.current_stats['start']).strftime('%d-%b %H:%M')

            self.current_stats['stop-str'] = '            '
            if isinstance(self.current_stats['stop'], datetime.datetime):
                self.current_stats['stop-str'] = self.config.in_output_tz(self.current_stats['stop']).strftime('%d-%b %H:%M')
            return self.current_stats

    def get_adding_stats(self, programs, group_slots = None):
        with self.node_lock:
            if isinstance(programs, ChannelNode):
                self.adding_stats = copy(programs.save_current_stats())
                if self.adding_stats['count'] == 0:
                    self.adding_list = []
                    return False

                else:
                    self.adding_list = programs.programs[:]
                    return True

            elif len(programs) == 0:
                self.adding_list = []
                return False

            else:
                self.adding_stats['count'] = len(programs)
                self.adding_list = programs[:]
                self.adding_stats['groups'] = 0
                try:
                    if isinstance(programs[0], ProgramNode):
                        programs.sort(key=lambda program: (program.start))
                        self.adding_stats['start'] = programs[0].start
                        self.adding_stats['stop'] = programs[-1].stop
                        if group_slots != None and len(group_slots) > 0:
                            self.adding_stats['groups'] = len(group_slots)
                            self.adding_stats['count'] += self.adding_stats['groups']
                            group_slots.sort(key=lambda program: (program.start))
                            if group_slots[0].start < self.adding_stats['start']:
                                self.adding_stats['start'] = group_slots[0].start

                            if group_slots[0].stop > self.adding_stats['stop']:
                                self.adding_stats['stop'] = group_slots[0].stop

                    else:
                        programs.sort(key=lambda program: (program['start-time']))
                        for i in range(len(programs)-1, 0, -1):
                            if not 'stop-time' in programs[i-1] or not isinstance(programs[i-1]['stop-time'], datetime.datetime):
                                programs[i-1]['stop-time'] = copy(programs[i]['start-time'])

                        self.adding_stats['start'] = programs[0]['start-time']
                        if 'stop-time' in programs[-1] and isinstance(programs[-1]['stop-time'], datetime.datetime):
                            self.adding_stats['stop'] = programs[-1]['stop-time']

                        else:
                            self.adding_stats['stop'] = programs[-1]['start-time']

                    self.adding_stats['start-str'] = '            '
                    if isinstance(self.adding_stats['start'], datetime.datetime):
                        self.adding_stats['start-str'] = self.config.in_output_tz(self.adding_stats['start']).strftime('%d-%b %H:%M')

                    self.adding_stats['stop-str'] = '            '
                    if isinstance(self.adding_stats['stop'], datetime.datetime):
                        self.adding_stats['stop-str'] = self.config.in_output_tz(self.adding_stats['stop']).strftime('%d-%b %H:%M')

                    return True

                except:
                    #~ traceback.print_exc()
                    self.adding_list = []
                    self.adding_stats['start'] = None
                    self.adding_stats['stop'] = None
                    self.adding_stats['count'] = 0
                    self.adding_stats['groups'] = 0
                    return False

    def init_merge_stats(self):
        with self.node_lock:
            self.match_array = []
            self.merge_stats['new'] = 0
            self.merge_stats['matched'] = 0
            self.merge_stats['groupslot'] = 0
            self.merge_stats['unmatched'] = 0
            self.merge_stats['genre'] = 0

    def add_stat(self, type = 'matched', addcnt = 1):
        with self.node_lock:
            if not type in self.merge_stats:
                self.merge_stats[type] = 0

            self.merge_stats[type] += addcnt

            if self.merge_stats[type] < 0:
                self.merge_stats[type] = 0

    def add_match_stat(self, type, pnode1, pnode2):
        with self.node_lock:
            if not (type & self.config.opt_dict['match_log_level']):
                return

            if isinstance(pnode1, ProgramNode):
                start_stop1 = pnode1.get_start_stop()
                title1 = pnode1.get_title()
                genre1 = pnode1.get_genre()

            else:
                start_stop1 = ''
                title1 = ''
                genre1 = ''

            if isinstance(pnode2, (ProgramNode, dict)):
                start_stop2 = self.get_start_stop(pnode2)
                title2 = self.get_title(pnode2)
                genre2 = self.get_genre(pnode2)

            else:
                start_stop2 = ''
                title2 = ''
                genre2 = ''

            # Added
            if type ==1:
                #~ mstr = self.config.text('fetch', 48)
                self.match_array.append(u'Added from %s:%s: %s Genre: %s.\n' % (self.adding_from.rjust(14), start_stop2, title2, genre2))

            # It was already there but not matched
            elif type == 33:
                type = 1
                #~ mstr = self.config.text('fetch', 46)
                self.match_array.append(u'Kept unmatched:           %s: %s Genre: %s.\n' % (start_stop1, title1, genre1))

            # Unmatched from the new source
            elif type == 2:
                #~ mstr = self.config.text('fetch', 50)
                self.match_array.append(u'Leftover in %s:%s: %s Genre: %s.\n' % (self.adding_from.rjust(13), start_stop2, title2, genre2))

            # Matched on title and time
            elif type == 4:
                #~ mstr = self.config.text('fetch', 29)
                self.match_array.append(u'Match from %s:%s: %s Genre: %s.\n' % (self.adding_from.rjust(14), start_stop2, title2, genre2))
                self.match_array.append(u'     on time and title to:%s: %s Genre: %s.\n' % (start_stop1, title1, genre1))

            elif type == 36:
                # For furure generic matches on Genre
                type = 4
                #~ mstr = self.config.text('fetch', 30)
                return

            # Added to a groupslot
            elif type == 8:
                #~ mstr = self.config.text('fetch', 47)
                self.match_array.append(u'      from %s:%s: %s Genre: %s.\n' % (self.adding_from.rjust(14), start_stop2, title2, genre2))

            # The groupslot
            elif type == 40:
                type = 8
                self.match_array.append(u'Added to groupslot:       %s: %s Genre: %s.\n' % (start_stop1, title1, genre1))

    def log_merge_statistics(self, source):
        with self.node_lock:
            # merge_types
            # 0/1 adding/merging
            # 0/2/4 source/filtered channel/unfiltered channel
            self.merge_stats['new'] -= self.merge_stats['groupslot']
            if self.merge_type & 1:
                mtype = self.config.text('IO', 2, type = 'stats')

            else:
                mtype = self.config.text('IO', 1, type = 'stats')

            log_array = ['\n']
            if isinstance(source, ChannelNode):
                addingid = source.chanid
                addingname = source.shortname
                stype = self.config.text('IO', 6, type = 'stats')
                sn = source.name

            else:
                addingid = source
                addingname = self.config.channelsource[source].source
                stype = self.config.text('IO', 5, type = 'stats')
                sn = source

            log_array.append(self.config.text('IO', 9, \
                (mtype, self.name , self.channel_config.counter, self.config.chan_count, stype, addingname), 'stats'))
            if self.merge_type & 1:
                log_array.append(self.config.text('IO', 10, \
                    (self.current_stats['count'], self.shortname.ljust(15), self.current_stats['start-str'], \
                    self.current_stats['stop-str'], self.current_stats['groups']), 'stats'))
            log_array.append(self.config.text('IO', 11, \
                (self.adding_stats['count'], addingname.ljust(15), self.adding_stats['start-str'], \
                self.adding_stats['stop-str'], self.adding_stats['groups']), 'stats'))
            log_array.append('\n')
            log_array.append(self.config.text('IO', 14, (self.merge_stats['matched'], ), 'stats'))
            log_array.append(self.config.text('IO', 12, (self.merge_stats['new'], ), 'stats'))
            log_array.append(self.config.text('IO', 15, (self.merge_stats['groupslot'], ), 'stats'))
            log_array.append(self.config.text('IO', 13, (self.merge_stats['genre'], ), 'stats'))
            log_array.append(self.config.text('IO', 16, (self.merge_stats['unmatched'], addingname), 'stats'))
            log_array.append(self.config.text('IO', 17, (self.program_count(), len(self.group_slots)), 'stats'))
            log_array.append(self.config.text('IO', 18, (len(self.programs_with_no_genre), ), 'stats'))
            log_array.append('\n')
            self.config.log(log_array, 4, 3)
            try:
                if self.config.write_info_files and (self.merge_type & 7):
                    self.config.infofiles.write_fetch_list(self, self.chanid, sn, self.name)

            except:
                traceback.print_exc()
                pass

            self.merge_type = None

    def program_count(self):
        return len(self.programs)

    def merge_source(self, programs, source):
        def add_to_list(dlist, pp, is_groupslot = False):
            pn = ProgramNode(self, source, pp)
            if pn.is_valid:
                pn.is_groupslot = is_groupslot
                dlist.append(pn)

        def check_gaps(pp, is_groupslot = False):
            if not 'stop-time' in pp or not isinstance(pp['stop-time'], datetime.datetime):
                return

            for gs in self.group_slots[:]:
                if gs.gs_start() <= pp['start-time'] <= gs.gs_stop() \
                  or gs.gs_start() <= pp['stop-time'] <= gs.gs_stop():
                    # if the groupslot is not detailed we only mark it matched
                    if not is_groupslot or len(gs.gs_detail) > 0:
                        add_to_list(gs.gs_detail, pp, is_groupslot)

                    #~ else:
                        #~ print is_groupslot, len(gs.gs_detail), self.chanid, source, pp['start-time'], '-', pp['stop-time']
                    break

            else:
                if pp['start-time'] < self.start:
                    add_to_list(add_to_start, pp, is_groupslot)
                    return

                if pp['stop-time'] > self.stop:
                    add_to_list(add_to_end, pp, is_groupslot)
                    return

                for pgap in self.program_gaps:
                    if pgap.is_overlap:
                        # This is a negative gap
                        continue

                    if pgap.start <= pp['start-time'] <= pgap.stop \
                      or pgap.start <= pp['stop-time'] <= pgap.stop:
                        # It falls into a gap
                        add_to_list(pgap.gap_detail, pp, is_groupslot)
                        break

                else:
                    # Unmatched
                    unmatched.append(pp)
                    self.config.infofiles.write_raw_string('%s, %s: %s - %s' % (source, self.chanid, self.config.in_output_tz(pp['start-time']).strftime('%d %b %H:%M'), self.config.in_output_tz(pp['stop-time']).strftime('%d %b %H:%M')))

        #Is it a valid source or does It look like a a channel merge
        if isinstance(programs, ChannelNode):
            self.merge_channel(programs)
            return

        # Is programs empty or is the source invalid?
        if not isinstance(programs, list) or len(programs) == 0 or not source in self.config.channelsource.keys():
            return

        with self.node_lock:
            self.save_current_stats()
            self.init_merge_stats()
            if not self.get_adding_stats(programs):
                return

            self.adding_from = self.config.channelsource[source].source
            # Is this the first source?
            if self.program_count() == 0:
                self.config.log(['\n', self.config.text('IO', 7, (self.config.text('IO', 3, type='stats'), \
                    self.adding_stats['count'], self.config.channelsource[source].source, self.current_stats['count'], self.name), 'stats'), \
                    self.config.text('IO', 8, (self.channel_config.counter, self.config.chan_count), 'stats')], 2)

                self.merge_type = 0
                last_stop = self.start
                previous_node = None
                for index in range(len(programs)):
                    # Check for renames
                    if programs[index]['name'].lower().strip() in self.config.channelprogram_rename[self.chanid].keys():
                        programs[index]['name'] = self.config.channelprogram_rename[self.chanid][programs[index]['name'].lower().strip()]

                    # Create the program node
                    pn = ProgramNode(self, source, programs[index])
                    if not pn.is_valid:
                        continue

                    if self.first_node == None:
                        self.first_node = pn
                        self.start = pn.start

                    # Link the nodes and check if there was a gap
                    gap =self.link_nodes(previous_node, pn)
                    if gap != None:
                        self.program_gaps.append(gap)

                    last_stop = pn.stop
                    previous_node = pn
                    self.add_new_program(pn)

                self.last_node = previous_node
                self.stop = last_stop
                self.adding_stats['groups'] = len(self.group_slots)
                self.log_merge_statistics(source)
                try:
                    if self.config.write_info_files:
                        self.config.infofiles.write_fetch_list(programs, self.chanid, source, self.name)

                except:
                    traceback.print_exc()
                    pass

            else:
                self.config.log(['\n', self.config.text('IO', 7, (self.config.text('IO', 4, type='stats'), \
                    self.adding_stats['count'], self.config.channelsource[source].source, self.current_stats['count'], self.name), 'stats'), \
                    self.config.text('IO', 8, (self.channel_config.counter, self.config.chan_count), 'stats')], 2)

                self.merge_type = 1
                group_slots = []
                add_to_start = []
                add_to_end = []
                unmatched = []

                # first we do some general renaming and filter out the groupslots
                for p in programs[:]:
                    if p['name'].lower().strip() in self.config.channelprogram_rename[self.chanid].keys():
                        p['name'] = self.config.channelprogram_rename[self.chanid][p['name'].lower().strip()]

                    p['mname'] = re.sub('[-,. ]', '', self.config.fetch_func.remove_accents(p['name']).lower()).strip()
                    # It's a groupslot
                    if p['mname'] in self.groupslot_names:
                        group_slots.append(p)
                        programs.remove(p)
                        continue

                try:
                    if self.config.write_info_files:
                        self.config.infofiles.write_fetch_list(programs, self.chanid, source, self.name, group_slots)

                except:
                    traceback.print_exc()
                    pass

                self.adding_stats['groups'] = len(group_slots)
                programs.sort(key=lambda program: (program['start-time']))
                # Try matching on time and name or check if it falls into a groupslot, a gap or outside the range
                for index in range(len(programs)):
                    for check in self.checkrange:
                        mstart = programs[index]['start-time'] + datetime.timedelta(0, 0, 0, 0, check)
                        if mstart in self.programs_by_start.keys() and self.programs_by_start[mstart].match_title(programs[index]['mname']):
                            # ### Check on split episodes
                            #~ l_diff = programs[index]['length'].total_seconds()/ self.programs_by_start[mstart].length.total_seconds()
                            #~ if l_diff >1.2 or l_diff < 1.2:
                                #~ pass

                            self.add_match_stat(4, self.programs_by_start[mstart], programs[index])
                            if self.programs_by_start[mstart] in self.current_list:
                                self.current_list.remove(self.programs_by_start[mstart])

                            self.programs_by_start[mstart].add_source_data(programs[index], source)
                            self.add_stat()
                            break

                    else:
                        check_gaps(programs[index])

                # Check if any new groupslot falls in a detailed groupslot or outside current range or in gaps
                if len(group_slots) > 0:
                    self.program_gaps.sort(key=lambda program: (program.start))
                    group_slots.sort(key=lambda program: (program['start-time']))
                    for index in range(len(group_slots)):
                        check_gaps(group_slots[index], True)

                # And add any program found new
                for gs in self.group_slots[:]:
                    self.fill_group(gs)

                self.fill_group(add_to_start)
                self.fill_group(add_to_end)
                for pgap in self.program_gaps[:]:
                    self.fill_group(pgap)

                self.add_stat('unmatched', len(unmatched))
                # Finally we check if we can add any genres
                self.check_on_missing_genres()
                for p in unmatched:
                    self.add_match_stat(2, None, p)

                for p in self.current_list:
                    self.add_match_stat(33, p, None)

                # Matching on genre?
                self.log_merge_statistics(source)
                self.config.log(self.match_array, 32, 3)

            self.adding_from = ''

    def merge_channel(self, channode):
        def add_to_list(dlist, pn):
            if pn.channode != self:
                pn = pn.copy(self)

            dlist.append(pn)

        def check_gaps(pn, add_always = True):
            for gs in self.group_slots[:]:
                if gs.gs_start() <= pn.start <= gs.gs_stop() \
                  or gs.gs_start() <= pn.stop <= gs.gs_stop():
                    # if the groupslot is not detailed we only mark it matched
                    if add_always or len(gs.gs_detail) > 0:
                        add_to_list(gs.gs_detail, pn)

                    break

            else:
                # Check if it falls outside current range
                if pn.start < self.start:
                    add_to_list(add_to_start, pn)
                    return

                if pn.stop > self.stop:
                    add_to_list(add_to_end, pn)
                    return

                for pgap in self.program_gaps:
                    if pgap.is_overlap:
                        # This is a negative gap
                        continue

                    if pgap.start <= pn.start <= pgap.stop \
                      or pgap.start <= pn.stop <= pgap.stop:
                        # It falls into a gap
                        add_to_list(pgap.gap_detail, pn)
                        break

                else:
                    # Unmatched
                    unmatched.append(pn)

        if not isinstance(channode, ChannelNode) or channode.program_count == 0:
            return

        with self.node_lock:
            self.save_current_stats()
            self.init_merge_stats()
            self.adding_from = channode.name
            programs = []
            group_slots = []
            add_to_start = []
            add_to_end = []
            unmatched = []
            pnode = channode.first_node
            if len(self.child_times) > 0:
                # We filter the nodes
                self.merge_type = 2
                for pzone in self.child_times:
                    if pzone['chanid'] == channode.chanid:
                        while True:
                            if not isinstance(pnode, ProgramNode):
                                # We reached the last node
                                break

                            if pnode.stop <= pzone['start']:
                                # Before the zone
                                pnode = pnode.next
                                continue

                            if pnode.start >= pzone['stop']:
                                # We passed the zone, so go to the next
                                break

                            # Copy the node
                            cnode = pnode.copy(self)
                            if cnode.start < pzone['start']:
                                # Truncate the start, but not it this is the start of the listing
                                if 'real-start' in pzone and isinstance(pzone['real-start'], datetime.datetime):
                                    if cnode.start < pzone['real-start']:
                                        cnode.adjust_start(pzone['real-start'])

                                else:
                                    cnode.adjust_start(pzone['start'])

                            if cnode.stop >pzone['stop']:
                                # Truncate the end, but not it this is the end of the listing, add the node and move to the next zone
                                if 'real-stop' in pzone and isinstance(pzone['real-stop'], datetime.datetime):
                                    if cnode.start > pzone['real-stop']:
                                        cnode.adjust_stop(pzone['real-stop'])

                                else:
                                    cnode.adjust_stop(pzone['stop'])

                                if cnode.is_groupslot:
                                    group_slots.append(cnode)

                                else:
                                    programs.append(cnode)

                                break

                            # Add the node
                            if cnode.is_groupslot:
                                group_slots.append(cnode)

                            else:
                                programs.append(cnode)

                            # And go to the next node
                            pnode = pnode.next

                    if not isinstance(pnode, ProgramNode):
                        # We reached the last node
                        break
                self.get_adding_stats(programs, group_slots)

            else:
                self.merge_type = 4
                self.get_adding_stats(channode)
                while isinstance(pnode, ProgramNode):
                    if pnode.is_groupslot:
                        group_slots.append(pnode)

                    else:
                        programs.append(pnode)

                    pnode = pnode.next

            if self.program_count() == 0:
                # We add
                self.config.log(['\n', self.config.text('IO', 7, (self.config.text('IO', 3, type='stats'), \
                    self.adding_stats['count'], channode.name, self.current_stats['count'], self.name), 'stats'), \
                    self.config.text('IO', 8, (self.channel_config.counter, self.config.chan_count), 'stats')], 2)

                programs.extend(group_slots)
                programs.sort(key=lambda pnode: (pnode.start))
                self.first_node = programs[0]
                self.last_node = programs[-1]
                self.start = self.first_node.start
                self.stop = self.last_node.stop
                for index in range(len(programs) - 1):
                    gap = self.link_nodes(programs[index], programs[index + 1])
                    if gap != None:
                        self.program_gaps.append(gap)

                    self.add_new_program(programs[index])

                self.add_new_program(self.last_node)

                self.log_merge_statistics(channode)
            else:
                # Try matching on time and name or check if it falls into a groupslot, a gap or outside the range
                self.config.log(['\n', self.config.text('IO', 7, (self.config.text('IO', 4, type='stats'), \
                    self.adding_stats['count'], channode.name, self.current_stats['count'], self.name), 'stats'), \
                    self.config.text('IO', 8, (self.channel_config.counter, self.config.chan_count), 'stats')], 2)

                self.merge_type += 1
                programs.sort(key=lambda pnode: (pnode.start))
                for index in range(len(programs)):
                    for check in self.checkrange:
                        mstart = programs[index].start + datetime.timedelta(0, 0, 0, 0, check)
                        if mstart in self.programs_by_start.keys() and self.programs_by_start[mstart].match_title(programs[index].match_name):
                            # ### Check on split episodes
                            #~ l_diff = programs[index].length.total_seconds()/ self.programs_by_start[mstart].length.total_seconds()
                            #~ if l_diff >1.2 or l_diff < 1.2:
                                #~ pass

                            self.add_match_stat(4, self.programs_by_start[mstart], programs[index])
                            if self.programs_by_start[mstart] in self.current_list:
                                self.current_list.remove(self.programs_by_start[mstart])

                            self.programs_by_start[mstart].add_node_data(programs[index])
                            self.add_stat()
                            break

                    else:
                        check_gaps(programs[index], True)

                # Check if any new groupslot falls in a detailed groupslot or outside current range or in gaps
                if len(group_slots) > 0:
                    self.program_gaps.sort(key=lambda program: (program.start))
                    group_slots.sort(key=lambda program: (program.start))
                    for index in range(len(group_slots)):
                        check_gaps(group_slots[index])

                # And add any program found new
                for gs in self.group_slots[:]:
                    self.fill_group(gs)

                self.fill_group(add_to_start)
                self.fill_group(add_to_end)
                for pgap in self.program_gaps[:]:
                    self.fill_group(pgap)

                self.add_stat('unmatched', len(unmatched))
                # Finally we check if we can add any genres
                self.check_on_missing_genres()
                for p in unmatched:
                    self.add_match_stat(2, None, p)

                for p in self.current_list:
                    self.add_match_stat(33, p, None)

                self.log_merge_statistics(channode)
                self.config.log(self.match_array, 32, 3)

            self.adding_from = ''

    def check_lineup(self, overlap_strategy = None):
        if overlap_strategy not in ['average', 'stop', 'start']:
            return

        with self.node_lock:
            # We check overlap
            for gap in self.program_gaps[:]:
                if gap.abs_length > self.max_overlap:
                    continue

                 # stop-time of previous program wins
                if overlap_strategy == 'stop':
                    gap.next.adjust_start(gap.start)

                # start-time of next program wins
                elif overlap_strategy == 'start':
                    gap.previous.adjust_stop(gap.stop)

                # average the difference
                elif overlap_strategy == 'average':
                    gap.next.adjust_start(gap.start + (gap.length // 2))
                    gap.previous.adjust_stop(gap.start + (gap.length // 2))

                self.remove_gap(gap)

            # Check Which Title/Subtitle combination wins
            #~ pnode = self.first_node
            #~ while isinstance(pnode, ProgramNode):

                #~ pnode = pnode.next

    def link_nodes(self, node1, node2, adjust_overlap = None):
        with self.node_lock:
            if isinstance(node1, ProgramNode):
                node1.next = node2

            if isinstance(node2, ProgramNode):
                node2.previous = node1

            if not isinstance(node1, ProgramNode) or not isinstance(node2, ProgramNode):
                return None

            node1.next_gap = None
            node2.previous_gap = None
            if node1.stop > node2.start:
                if adjust_overlap == 'stop':
                    node1.adjust_stop(node2.start)

                elif adjust_overlap == 'start':
                    node2.adjust_start(node1.stop)

            if abs(node2.start - node1.stop) > self.max_overlap:
                gap = GapNode(self, node1, node2)
                return gap

    def fill_group(self, pgrp):
        with self.node_lock:
            if isinstance(pgrp, ProgramNode):
                if len(pgrp.gs_detail) == 0:
                    return

                self.add_stat('groupslot', len(pgrp.gs_detail))
                gtype = 'gs'
                gdetail = pgrp.gs_detail
                gprevious = pgrp.previous
                gnext = pgrp.next
                self.add_match_stat(40, pgrp, None)
                for p in gdetail:
                    self.add_match_stat(8, None, p)

                if pgrp in self.current_list:
                    self.current_list.remove(pgrp)

            elif isinstance(pgrp, GapNode):
                if len(pgrp.gap_detail) == 0:
                    return

                gtype = 'gap'
                gdetail = pgrp.gap_detail
                gprevious = pgrp.previous
                gnext = pgrp.next

            elif isinstance(pgrp, list):
                if len(pgrp) == 0:
                    return

                for pn in pgrp:
                    if not isinstance(pn, ProgramNode):
                        return

                gtype = 'list'
                gdetail = pgrp
                gprevious = None
                gnext = None

            else:
                return

            # We replace the group with the details
            gdetail.sort(key=lambda program: (program.start))
            if pgrp == self.first_node or gdetail[0].start < self.first_node.start:
                # Is this group the first Item?
                if gnext == None:
                    gnext = self.first_node

                self.first_node = gdetail[0]
                self.start = gdetail[0].start + datetime.timedelta(seconds = 5)

            if pgrp == self.last_node or gdetail[-1].stop > self.last_node.stop:
                # Or the last Item
                if gprevious == None:
                    gprevious = self.last_node

                self.last_node = gdetail[-1]
                self.stop = gdetail[-1].stop - datetime.timedelta(seconds = 5)

            # Remove any old Gap or Group
            if gtype == 'gap':
                self.remove_gap(pgrp)

            elif gtype == 'gs':
                self.remove_gs(pgrp)
                self.remove_gap(pgrp.previous_gap)
                self.remove_gap(pgrp.next_gap)

            start_gap = self.link_nodes(gprevious, gdetail[0], 'start')
            stop_gap = self.link_nodes(gdetail[-1], gnext, 'stop')
            for index in range(1, len(gdetail)):
                gap = self.link_nodes(gdetail[index - 1], gdetail[index])
                if gap != None:
                    self.program_gaps.append(gap)

            for pn in gdetail:
                self.add_new_program(pn)

            if start_gap != None:
                self.program_gaps.append(start_gap)

            if stop_gap != None:
                self.program_gaps.append(stop_gap)

    def remove_gs(self, gs):
        if not isinstance(gs, ProgramNode):
            return

        with self.node_lock:
            if isinstance(gs.next, ProgramNode):
                gs.next.previous = None
                gs.next = None
                gs.next_gap = None

            if isinstance(gs.previous, ProgramNode):
                gs.previous.next = None
                gs.previous = None
                gs.previous_gap = None

            if gs in self.group_slots:
                self.group_slots.remove(gs)

            if gs in self.programs:
                self.programs.remove(gs)

    def remove_gap(self, pgap):
        if not isinstance(pgap, GapNode):
            return

        with self.node_lock:
            if isinstance(pgap.next, ProgramNode):
                pgap.next.previous_gap = None
                pgap.next = None

            if isinstance(pgap.previous, ProgramNode):
                pgap.previous.next_gap = None
                pgap.previous = None

            if pgap in self.program_gaps:
                self.program_gaps.remove(pgap)

    def add_new_program(self,pn):
        with self.node_lock:
            if not pn in self.programs:
                self.programs.append(pn)
                self.add_stat('new', 1)
                self.add_match_stat(1, None, pn)

            # Check if it has a groupslot name
            if pn.match_name in self.groupslot_names:
                self.group_slots.append(pn)
                pn.is_groupslot = True
                return

            self.programs_by_start[pn.start] = pn
            self.programs_by_stop[pn.stop] = pn
            if pn.name in self.programs_by_name.keys():
                self.programs_by_name[pn.name].append(pn)

            else:
                self.programs_by_name[pn.name] = [pn]

            if pn.match_name in self.programs_by_matchname.keys():
                self.programs_by_matchname[pn.match_name].append(pn)

            else:
                self.programs_by_matchname[pn.match_name] = [pn]

            if not pn.is_set('genre') or pn.get_value('genre').lower().strip() in ('', self.config.cattrans_unknown.lower().strip()):
                if pn.match_name in self.programs_with_no_genre.keys():
                    self.programs_with_no_genre[pn.match_name].append(pn)

                else:
                    self.programs_with_no_genre[pn.match_name] = [pn]

    def check_on_missing_genres(self):
        # Check if we can match any program without genre to one similar named with genre
        with self.node_lock:
            name_remove = []
            for k, pl in self.programs_with_no_genre.items():
                if len(pl) >= self.programs_by_matchname[k]:
                    continue

                for pn in self.programs_by_matchname[k]:
                    if pn.is_set('genre') and pn.get_value('genre').lower().strip() not in ('', self.config.cattrans_unknown.lower().strip()):
                        for pg in pl:
                            pg.set_value('genre', pn.get_value('genre'))
                            pg.set_value('subgenre', pn.get_value('subgenre'))
                            self.add_stat('genre', 1)

                        name_remove.append(k)
                        break

            for k in name_remove:
                if k in self.programs_with_no_genre.keys():
                    del self.programs_with_no_genre[k]

    def get_start_stop(self, tdict, printable=True):
        with self.node_lock:
            if isinstance(tdict, ProgramNode):
                pstart = self.config.in_output_tz(tdict.start)
                pstop = self.config.in_output_tz(tdict.stop)
                if printable and tdict.is_groupslot:
                    return '#%s - %s' % (pstart.strftime('%d %b %H:%M'), pstop.strftime('%d %b %H:%M'))

            elif isinstance(tdict, dict) and 'start-time' in tdict and 'stop-time' in tdict:
                pstart = self.config.in_output_tz(tdict['start-time'])
                pstop = self.config.in_output_tz(tdict['stop-time'])

            else:
                return

            if printable:
                return ' %s - %s' % (pstart.strftime('%d %b %H:%M'), pstop.strftime('%d %b %H:%M'))

            return (pstart, pstop)

    def get_title(self, tdict, printable=True):
        with self.node_lock:
            if isinstance(tdict, ProgramNode):
                title = tdict.get_value('title')

            elif isinstance(tdict, dict) and 'name' in tdict and 'episode title' in tdict:
                title = (tdict['name'], tdict['episode title'])

            elif isinstance(tdict, dict) and 'name' in tdict:
                title = (tdict['name'], '')

            else:
                return

            if printable and title[1] == '':
                return '%s:---' % title[0]

            if printable:
                return '%s: %s' % title

            return title

    def get_genre(self, tdict):
        with self.node_lock:
            if isinstance(tdict, ProgramNode):
                g = tdict.get_value('genre')
                sg = tdict.get_value('subgenre')

            elif isinstance(tdict, dict):
                if 'genre' in tdict:
                    g = tdict['genre']

                else:
                    g = self.config.cattrans_unknown.lower().strip()

                if 'subgenre' in tdict:
                    sg = tdict['subgenre']

                else:
                    sg = ''

            else:
                return

            if self.channel_config.opt_dict['cattrans']:
                cat0 = ('', '')
                cat1 = (g.lower(), '')
                cat2 = (g.lower(), sg.lower())
                if cat2 in self.config.cattrans.keys() and self.config.cattrans[cat2] != '':
                    cat = self.config.cattrans[cat2].capitalize()

                elif cat1 in self.config.cattrans.keys() and self.config.cattrans[cat1] != '':
                    cat = self.config.cattrans[cat1].capitalize()

                elif cat0 in self.config.cattrans.keys() and self.config.cattrans[cat0] != '':
                   cat = self.config.cattrans[cat0].capitalize()

                else:
                    cat = 'Unknown'

                return cat

            elif g == '':
                return self.config.cattrans_unknown.capitalize().strip()

            else:
                return g.capitalize()

# end ChannelNode

class ProgramNode():
    def __init__(self, channode, source, data):
        if not isinstance(channode, ChannelNode):
            self.is_valid = False
            return

        self.node_lock = RLock()
        with self.node_lock:
            self.channode = channode
            self.config = channode.config
            self.channel_config = channode.channel_config
            self.start = None
            self.stop = None
            self.length = None
            self.name = None
            self.match_name = None
            self.previous = None
            self.next = None
            self.previous_gap = None
            self.next_gap = None
            self.is_groupslot = False
            self.gs_detail = []
            self.tdict = {}
            self.matchobject = difflib.SequenceMatcher(isjunk=lambda x: x in " '\",.-/", autojunk=False)
            self.first_source = True
            if isinstance(data, dict):
                self.is_valid =  self.add_source_data(data, source)

            else:
                self.is_valid = False

    def is_set(self, key):
        if key in self.tdict:
            return True

        if key == 'credits':
            for k in self.config.key_values['credits']:
                if k in self.tdict and len(self.tdict[k]['prime']) > 0:
                    return True

        elif key == 'video':
            for k in self.config.key_values['video']:
                if k in self.tdict:
                    return True

        return False

    def adjust_start(self, pstart):
        with self.node_lock:
            if self.start in self.channode.programs_by_start.keys():
                del self.channode.programs_by_start[self.start]

            self.start = copy(pstart).replace(second = 0, microsecond = 0)
            self.channode.programs_by_start[self.start] = self
            self.tdict['start-time']['prime'] = self.start
            self.length = self.stop - self.start
            self.tdict['length']['prime'] = self.length
            if isinstance(self.previous_gap, GapNode):
                self.previous_gap.adjust_stop(self.start)

    def adjust_stop(self, pstop):
        with self.node_lock:
            if self.stop in self.channode.programs_by_stop.keys():
                del self.channode.programs_by_stop[self.stop]

            self.stop = copy(pstop).replace(second = 0, microsecond = 0)
            self.channode.programs_by_stop[self.stop] = self
            self.tdict['stop-time']['prime'] = self.stop
            self.length = self.stop - self.start
            self.tdict['length']['prime'] = self.length
            if isinstance(self.next_gap, GapNode):
                self.next_gap.adjust_start(self.stop)

    def gs_start(self):
        if self.is_groupslot and isinstance(self.previous_gap, GapNode):
            return self.previous_gap.start

        else:
            return self.start

    def gs_stop(self):
        if self.is_groupslot and isinstance(self.next_gap, GapNode):
            return self.next_gap.stop

        else:
            return self.stop

    def match_title(self, mname, submname = ''):
        if self.match_name == mname:
            return True

        if len(self.match_name) < len(mname) and self.match_name in mname:
            return True

        if len(mname) < len(self.match_name) and mname in self.match_name:
            return True

        self.matchobject.set_seqs(self.match_name, mname)
        if self.matchobject.ratio() > .8:
            return True

        return False
    def add_source_data(self, data, source):
        if not source in self.config.channelsource.keys() or not isinstance(data, dict):
            return

        with self.node_lock:
            if self.first_source:
                for k in ('start-time', 'stop-time', 'length', 'name', 'title', 'genres'):
                    self.init_key_value(k)

                self.start = data['start-time'].replace(second = 0, microsecond = 0)
                if 'stop-time' in data and isinstance(data['stop-time'], datetime.datetime):
                    self.adjust_stop(data['stop-time'])

                elif 'length'  in data and isinstance(data['length'], datetime.timedelta):
                    self.adjust_stop(self.start + data['length'])

                else:
                    return False

                self.name = data['name']
                self.match_name = re.sub('[-,. ]', '', self.config.fetch_func.remove_accents(data['name']).lower()).strip()
            else:
                # Check if the new source is longer and if so extend over any gap
                start_diff = (self.start - data['start-time'])
                if start_diff.total_seconds() > 0:
                    if self.previous_gap != None and not self.previous_gap.is_overlap:
                        if data['start-time'] <= self.previous_gap.start:
                            # We add the gap to the program
                            self.adjust_start(self.previous_gap.start.replace(second = 0, microsecond = 0))
                            self.channode.remove_gap(self.previous_gap)

                        else:
                            # We reduce the gap
                            self.adjust_start(data['start-time'].replace(second = 0, microsecond = 0))
                            self.previous_gap.adjust_stop(self.start)

                    elif self.previous == None and start_diff < self.channode.max_overlap:
                        # It's the first program
                        self.adjust_start(data['start-time'].replace(second = 0, microsecond = 0))

                if 'stop-time' in data and isinstance(data['stop-time'], datetime.datetime):
                    stop_diff = (data['stop-time'] - self.stop)
                    if stop_diff.total_seconds() > 0:
                        if self.next_gap != None and not self.next_gap.is_overlap:
                            if data['stop-time'] >= self.next_gap.stop:
                                # We add the gap to the program
                                self.adjust_stop(self.next_gap.stop.replace(second = 0, microsecond = 0))
                                self.channode.remove_gap(self.next_gap)

                            else:
                                # We reduce the gap
                                self.adjust_stop(data['stop-time'].replace(second = 0, microsecond = 0))
                                self.next_gap.adjust_start(self.stop)

                        elif self.next == None and stop_diff < self.channode.max_overlap:
                            # It's the last program
                            self.adjust_stop(data['stop-time'].replace(second = 0, microsecond = 0))

            self.length = self.stop - self.start
            # Check for allowed key values
            if "episode title" in data.keys():
                data['title'] = (data['name'], data['episode title'])

            else:
                data['title'] = (data['name'], '')

            if 'genre' in data.keys():
                if "subgenre" in data.keys():
                    data['genres'] = (data['genre'], data['subgenre'])

                else:
                    data['genres'] = (data['genre'], '')

            for k, v in data.items():
                if k in ('credits', 'video'):
                    for k2, v2 in v.items():
                        if k2 in self.config.key_values[k]:
                            self.set_value(k2, v2, source)

                elif k in self.channode.key_list:
                    self.set_value(k, v, source)

            self.first_source = False
            return True

    def add_node_data(self, pnode):
        if not isinstance(pnode, ProgramNode):
            return

        with self.node_lock:
            if self.first_source:
                for k in ('start-time', 'stop-time', 'length', 'name', 'title', 'genres'):
                    self.init_key_value(k)

                self.start = pnode.start
                if isinstance(pnode.stop, datetime.datetime):
                    self.stop = pnode.stop
                    self.length = self.stop - self.start

                elif 'stop-time' in pnode.tdict.keys() and isinstance(pnode.tdict['stop-time']['prime'], datetime.datetime):
                    self.stop = pnode.tdict['stop-time']['prime'].replace(second = 0, microsecond = 0)
                    self.length = self.stop - self.start

                elif 'length'  in  pnode.tdict.keys() and isinstance(pnode.tdict['length']['prime'], datetime.timedelta):
                    self.length = pnode.tdict['length']['prime']
                    self.stop = (self.start + self.length).replace(second = 0, microsecond = 0)

                else:
                    return False

                self.name = pnode.name
                self.match_name = pnode.match_name

            else:
                # Check if the new node is longer and if so extend over any gap
                start_diff = (self.start - pnode.start)
                if start_diff.total_seconds() > 0:
                    if self.previous_gap != None and not self.previous_gap.is_overlap:
                        if pnode.start <= self.previous_gap.start:
                            # We add the gap to the program
                            self.adjust_start(self.previous_gap.start.replace(second = 0, microsecond = 0))
                            self.channode.remove_gap(self.previous_gap)

                        else:
                            # We reduce the gap
                            self.adjust_start(pnode.start.replace(second = 0, microsecond = 0))
                            self.previous_gap.adjust_stop(self.start)

                    elif self.previous == None and start_diff < self.channode.max_overlap:
                        # It's the first program
                        self.adjust_start(pnode.start.replace(second = 0, microsecond = 0))

                stop_diff = (pnode.stop - self.stop)
                if stop_diff.total_seconds() > 0:
                    if self.next_gap != None and not self.next_gap.is_overlap:
                        if pnode.stop >= self.next_gap.stop:
                            # We add the gap to the program
                            self.adjust_stop(self.next_gap.stop.replace(second = 0, microsecond = 0))
                            self.channode.remove_gap(self.next_gap)

                        else:
                            # We reduce the gap
                            self.adjust_stop(pnode.stop.replace(second = 0, microsecond = 0))
                            self.next_gap.adjust_start(self.stop)

                    elif self.next == None and stop_diff < self.channode.max_overlap:
                        # It's the last program
                        self.adjust_stop(pnode.stop.replace(second = 0, microsecond = 0))

            self.length = self.stop - self.start
            # Check for allowed key values
            for key, v in pnode.tdict.items():
                value = pnode.get_value(key)
                if not self.is_set(key):
                    self.tdict[key] = copy(v)
                    continue

                for source, value in v['sources'].items():
                    self.set_value(key, value, source)

            self.first_source = False

    def init_key_value(self, key):
        if not self.is_set(key):
            self.tdict[key] = {}
            self.tdict[key]['sources'] = {}
            self.tdict[key]['channels'] = {}
            self.tdict[key]['values'] = []
            self.tdict[key]['rank'] = []

    def set_source_value(self, key, source = None, value = None, force_prime = None):
        self.init_key_value(key)
        if value != None:
            if source in self.config.channelsource.keys():
                self.tdict[key]['sources'][source] = value

            elif source in self.config.channels.keys():
                self.tdict[key]['channels'][source] = value

        if force_prime != None:
            self.tdict[key]['prime'] = force_prime

        elif not 'prime' in self.tdict[key].keys() and value != None:
            self.tdict[key]['prime'] = value

    def set_value(self, key, value, source=None):
        def add_value(value):
            if key in ( "ID", "detail_url", "start-time", "stop-time", "length", "offset",
                            "name","episode title","originaltitle","genre", "subgenre"):
                # These are further handled separately, but make sure that at least a value is returned
                self.set_source_value(key, source, value)

            elif key == "prog_ID":
                if not self.is_set(key):
                    self.set_source_value(key, source, value)

                else:
                    for s in self.config.detail_sources:
                        if s == source:
                            self.set_source_value(key, source, value, value)
                            break

                        elif(s in self.tdict[key]['sources'].keys() and self.tdict[key]['sources'][s] != ''):
                            self.set_source_value(key, source, value)
                            break

                    else:
                        self.set_source_value(key, source, value)

            elif key in self.config.key_values['credits']:
                if isinstance(value, (dict, str, unicode)):
                    value = [value]

                self.set_source_value(key, source, value)
                if not 'prime names' in self.tdict[key].keys():
                    self.tdict[key]['prime names'] = []
                    self.tdict[key]['prime'] = []

                if isinstance(value, list):
                    for v in value:
                        if key in ("actor", "guest"):
                            if not isinstance(v, dict):
                                continue

                            if v['name'].lower() in self.tdict[key]['prime names']:
                                if v['role'] == None:
                                    continue

                                for index in range(len(self.tdict[key]['prime'])):
                                    if self.tdict[key]['prime'][index]['name'].lower() == v['name'].lower():
                                        if self.tdict[key]['prime'][index]['role'] == None:
                                            self.tdict[key]['prime'][index]['role'] = v['role']

                            else:
                                self.tdict[key]['prime names'].append(v['name'].lower())
                                self.tdict[key]['prime'].append(v)

                        elif not v in self.tdict[key]['prime']:
                            self.tdict[key]['prime'].append(v)

            elif key in ("country", "rating"):
                if self.is_set(key):
                    self.set_source_value(key, source, value)

                else:
                    self.set_source_value(key, source, value)
                    self.tdict[key]['prime'] = []

                if not isinstance(value, list):
                    value = [value]

                for v in value:
                    if not v.lower() in self.tdict[key]['prime']:
                        self.tdict[key]['prime'].append(v.lower())

            elif key == 'description':
                if source != None and self.channel_config.opt_dict['prefered_description'] == source and len(value) > 100:
                    self.tdict[key]['preferred'] = True
                    self.set_source_value(key, source, value, value)

                elif self.is_set(key) and not 'preferred' in self.tdict[key].keys() and len(value) > len(self.get_value(key)):
                    self.set_source_value(key, source, value, value)

                else:
                    self.set_source_value(key, source, value)

            elif key in self.config.key_values['bool'] or key in self.config.key_values['video']:
                self.set_source_value(key, source, value)
                if value:
                    self.tdict[key]['prime'] = True

            else:
                # Get the most common value
                self.set_source_value(key, source, value)
                for index in range(len(self.tdict[key]['values'])):
                    if value == self.tdict[key]['values'][index]:
                        self.tdict[key]['rank'][index] += 1
                        break

                else:
                    self.tdict[key]['values'].append(value)
                    self.tdict[key]['rank'].append(1)

                vcnt = 0
                for index in range(len(self.tdict[key]['values'])):
                    if self.tdict[key]['rank'][index] > vcnt:
                        if key in ('season', 'episode') and self.tdict[key]['values'][index] == 0:
                            continue

                        #~ if key in ('title', 'genres') and self.tdict[key]['values'][index][1] == '':
                            #~ continue

                        vcnt= self.tdict[key]['rank'][index]
                        self.tdict[key]['prime'] = self.tdict[key]['values'][index]

        with self.node_lock:
            if self.channode.merge_type & 6:
                add_value(value)
                return

            # basic validation of the values
            if value in ('', None) or (key == 'genre' and value.lower().strip() == self.config.cattrans_unknown.lower().strip()):
                return

            if key in self.config.key_values['text']:
                if isinstance(value, list):
                    if len(value) == 0:
                        return

                    elif len(value) == 1:
                        value = value[0]

                    else:
                        for item in range(len(value)):
                            if isinstance(value[item], str):
                                value[item] = unicode(value[item])

                if isinstance(value, str):
                    value = unicode(value)

                if key == 'country':
                    rlist = []
                    if isinstance(value, unicode):
                        cd = re.split('[,()/]', re.sub('\.', '', value).upper())
                        for cstr in cd:
                            if cstr in self.config.coutrytrans.values():
                                rlist.append(cstr)

                            elif cstr in self.config.coutrytrans.keys():
                                rlist.append(self.config.coutrytrans[cstr])

                            elif self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(u'new country => %s' % (cstr))

                    elif isinstance(value, (list,tuple)):
                        for item in value:
                            if not isinstance(item, unicode):
                                continue

                            cd = re.split('[,()/]', re.sub('\.', '', item).upper())
                            for cstr in cd:
                                if cstr == '':
                                    continue

                                if cstr in self.config.coutrytrans.values():
                                    rlist.append(cstr)

                                elif cstr in self.config.coutrytrans.keys():
                                    rlist.append(self.config.coutrytrans[cstr])

                                elif self.config.write_info_files:
                                    self.config.infofiles.addto_detail_list(u'new country => %s' % (cstr))

                    if len(rlist) > 0:
                        add_value(rlist)

                    return

                elif key == 'premiere year':
                    value = re.sub('[()]', '', value).strip()
                    if isinstance(value, unicode) and len(value) == 4:
                        try:
                            x = int(value)
                            add_value(value)

                        except:
                            return

                    return

                elif key == 'broadcaster':
                    add_value(re.sub('[()]', '', value).strip())
                    return

                elif key == 'description':
                    add_value(value)
                    return

            elif key in self.config.key_values['datetime']:
                if not isinstance(value, datetime.datetime):
                    return

            elif key in self.config.key_values['timedelta']:
                if not isinstance(value, datetime.timedelta):
                    return

            elif key in self.config.key_values['date']:
                if not isinstance(value, datetime.date):
                    return

            elif key in self.config.key_values['bool'] or key in self.config.key_values['video']:
                if not isinstance(value, bool):
                    return

            elif key in self.config.key_values['int']:
                if not isinstance(value, int):
                    return

            add_value(value)

    def get_value(self, key, source = None):
        if key == 'start':
            return self.config.in_output_tz(self.start).strftime('%d %b %H:%M')

        if key == 'stop':
            return self.config.in_output_tz(self.stop).strftime('%d %b %H:%M')

        if key == 'ID':
            if "prog_ID" in self.tdict.keys():
                return self.tdict["prog_ID"]['prime']

            return "---"

        if key in self.tdict:
            if source in self.tdict[key]['sources']:
                v = self.tdict[key]['sources'][source]

            elif source in self.tdict[key]['channels']:
                v = self.tdict[key]['channels'][source]

            else:
                v = self.tdict[key]['prime']

            if key == 'country' and isinstance(v, list):
                if len(v) > 0:
                    return v[0]

                else:
                    return u''

            return v

        # Set the return values on empty
        if key == 'genre':
            return self.config.cattrans_unknown.lower().strip()

        elif key in self.config.key_values['text']:
            return u''

        elif key in self.config.key_values['timedelta']:
            return datetime.timedelta(0)

        elif key in self.config.key_values['bool'] or key in self.config.key_values['video']:
            return False

        elif key in self.config.key_values['int']:
            return 0

        else:
            return u''

    def get_start_stop(self, printable=True):
        return self.channode.get_start_stop(self, printable)

    def get_title(self, printable=True):
        return self.channode.get_title(self, printable)

    def get_genre(self):
        return self.channode.get_genre(self)

    def get_description(self):
        desc_line = u''
        with self.node_lock:
            if self.is_set('subgenre'):
                sg = self.get_value('subgenre')
                if sg != '':
                    desc_line = u'%s: ' % (sg)

            if self.is_set('broadcaster'):
                bc = self.get_value('broadcaster')
                if bc != '':
                    desc_line = u'%s(%s) ' % (desc_line, bc)

            if self.is_set('description'):
                desc_line = u'%s%s ' % (desc_line, self.get_value('description'))

            # Limit the length of the description
            if desc_line != '':
                desc_line = re.sub('\n', ' ', desc_line)
                if len(desc_line) > self.channel_config.opt_dict['desc_length']:
                    spacepos = desc_line[0:self.channel_config.opt_dict['desc_length']-3].rfind(' ')
                    desc_line = desc_line[0:spacepos] + '...'

        return desc_line.strip()

    def copy(self, channode):
        if not isinstance(channode, ChannelNode):
            return

        with self.node_lock:
            new_pnode = ProgramNode(channode, None, None)
            new_pnode.tdict = deepcopy(self.tdict)
            new_pnode.start = new_pnode.tdict['start-time']['prime']
            new_pnode.stop = new_pnode.tdict['stop-time']['prime']
            new_pnode.length = new_pnode.tdict['length']['prime']
            new_pnode.name = copy(self.name)
            new_pnode.match_name = copy(self.match_name)
            new_pnode.is_groupslot = self.is_groupslot
            new_pnode.gs_detail = deepcopy(self.gs_detail)
            new_pnode.first_source = False
            new_pnode.is_valid = True
            return new_pnode

# end ProgramNode

class GapNode():
    def __init__(self, channode, previous_node, next_node):
        if not isinstance(channode, ChannelNode):
            self.is_valid = False
            return

        self.node_lock = RLock()
        with self.node_lock:
            self.channode = channode
            self.config = channode.config
            self.channel_config = channode.channel_config
            self.previous = previous_node
            self.next = next_node
            self.gap_detail = []
            self.is_overlap = False
            if isinstance(self.previous, ProgramNode):
                self.start = copy(self.previous.stop)
                self.previous.next_gap = self

            if isinstance(self.next, ProgramNode):
                self.adjust_stop(self.next.start)
                self.next.previous_gap = self

    def get_start_stop(self, printable=True):
        with self.node_lock:
            pstart = self.config.in_output_tz(self.start)
            pstop = self.config.in_output_tz(self.stop)
            if printable:
                return ' #%s - %s' % (pstart.strftime('%d %b %H:%M'), pstop.strftime('%d %b %H:%M'))

            return (pstart, pstop)

    def adjust_start(self, pstart):
        with self.node_lock:
            self.start = copy(pstart).replace(second = 0, microsecond = 0)
            self.length = None
            self.abs_length = None
            self.is_overlap = False
            if isinstance(self.start, datetime.datetime) and isinstance(self.stop, datetime.datetime):
                self.length = self.stop - self.start
                self.abs_length = abs(self.length)
                if self.stop < self.start:
                    self.is_overlap = True

    def adjust_stop(self, pstop):
        with self.node_lock:
            self.stop = copy(pstop).replace(second = 0, microsecond = 0)
            self.length = None
            self.abs_length = None
            self.is_overlap = False
            if isinstance(self.start, datetime.datetime) and isinstance(self.stop, datetime.datetime):
                self.length = self.stop - self.start
                self.abs_length = abs(self.length)
                if self.stop < self.start:
                    self.is_overlap = True

# end GapNode

class XMLoutput():
    '''
    This class collects the data and creates the output
    '''
    def __init__(self, config):

        self.config = config
        self.xmlencoding = 'UTF-8'
        # Thes will contain the seperate XML strings
        self.xml_channels = {}
        self.xml_programs = {}
        self.progress_counter = 0

        # We have several sources of logos, the first provides the nice ones, but is not
        # complete. We use the tvgids logos to fill the missing bits.
        self.logo_source_preference = []
        self.logo_provider = {}

        self.output_lock = Lock()
        self.cache_return = Queue()

        self.cache_count = 0
        self.fetch_count = 0
        self.fail_count = 0
        self.ttvdb_count = 0
        self.ttvdb_fail_count = 0
        self.program_count = 0

    def xmlescape(self, s):
        """Escape <, > and & characters for use in XML"""
        return saxutils.escape(s)

    def format_timezone(self, td, only_date=False ):
        """
        Given a datetime object, returns a string in XMLTV format
        """
        if not self.config.opt_dict['use_utc']:
            td = self.config.in_output_tz(td)

        if only_date:
            return td.strftime('%Y%m%d')

        else:
            return td.strftime('%Y%m%d%H%M%S %z')

    def add_starttag(self, tag, ident = 0, attribs = '', text = '', close = False):
        '''
        Add a starttag with optional attributestring, textstring and optionally close it.
        Give it the proper ident.
        '''
        if attribs != '':
            attribs = ' %s' % attribs

        if close and text == '':
            return u'%s<%s%s/>\n' % (''.rjust(ident), self.xmlescape(tag), self.xmlescape(attribs))

        if close and text != '':
            return u'%s<%s%s>%s</%s>\n' % (''.rjust(ident), self.xmlescape(tag), self.xmlescape(attribs), self.xmlescape(text), self.xmlescape(tag))

        else:
            return u'%s<%s%s>%s\n' % (''.rjust(ident), self.xmlescape(tag), self.xmlescape(attribs), self.xmlescape(text))

    def add_endtag(self, tag, ident = 0):
        '''
        Return a proper idented closing tag
        '''
        return u'%s</%s>\n' % (''.rjust(ident), self.xmlescape(tag))

    def create_channel_strings(self, chanid, add_HD = None):
        '''
        Create the strings for the channels we fetched info about
        '''
        if add_HD == True:
            xmltvid = '%s-hd' % self.config.channels[chanid].xmltvid

        else:
            xmltvid = self.config.channels[chanid].xmltvid

        self.xml_channels[xmltvid] = []
        self.xml_channels[xmltvid].append(self.add_starttag('channel', 2, 'id="%s%s"' % \
            (xmltvid, self.config.channels[chanid].opt_dict['compat'] and '.tvgids.nl' or '')))
        self.xml_channels[xmltvid].append(self.add_starttag('display-name', 4, 'lang="%s"' % (self.config.xml_language), \
            self.config.channels[chanid].chan_name, True))
        if (self.config.channels[chanid].opt_dict['logos']):
            if self.config.channels[chanid].icon_source in self.logo_provider.keys():
                lpath = self.logo_provider[self.config.channels[chanid].icon_source]
                lname = self.config.channels[chanid].icon
                if self.config.channels[chanid].icon_source == 5 and lpath[-16:] == 'ChannelLogos/02/':
                    if len(lname) > 16 and  lname[0:16] == 'ChannelLogos/02/':
                        lname = lname[16:].split('?')[0]

                    else:
                        lname = lname.split('?')[0]

                elif self.config.channels[chanid].icon_source == 5 and lpath[-16:] != 'ChannelLogos/02/':
                    if len(lname) > 16 and  lname[0:16] == 'ChannelLogos/02/':
                        lname = lname.split('?')[0]

                    else:
                        lpath = lpath + 'ChannelLogos/02/'
                        lname = lname.split('?')[0]

                full_logo_url = lpath + lname
                self.xml_channels[xmltvid].append(self.add_starttag('icon', 4, 'src="%s"' % full_logo_url, '', True))

            elif self.config.channels[chanid].icon_source == 99:
                self.xml_channels[xmltvid].append(self.add_starttag('icon', 4, 'src="%s"' % self.config.channels[chanid].icon, '', True))

        self.xml_channels[xmltvid].append(self.add_endtag('channel', 2))

    def create_program_string(self, chanid, add_HD = None):
        '''
        Create all the program strings
        '''
        if add_HD == True:
            xmltvid = '%s-hd' % self.config.channels[chanid].xmltvid

        else:
            xmltvid = self.config.channels[chanid].xmltvid
            with self.output_lock:
                self.program_count += len(self.config.channels[chanid].all_programs)

        self.xml_programs[xmltvid] = []
        channel_node = self.config.channels[chanid].channel_node
        if not isinstance(channel_node, ChannelNode):
            return
        program = channel_node.first_node
        while isinstance(program, ProgramNode):
            xml = []

            # Start/Stop
            attribs = 'start="%s" stop="%s" channel="%s%s"' % \
                (self.format_timezone(program.start), self.format_timezone(program.stop), \
                xmltvid, self.config.channels[chanid].opt_dict['compat'] and self.config.compat_text or '')

            #~ if 'clumpidx' in program and program['clumpidx'] != '':
                #~ attribs += 'clumpidx="%s"' % program['clumpidx']

            xml.append(self.add_starttag('programme', 2, attribs))

            # Title
            xml.append(self.add_starttag('title', 4, 'lang="%s"' % (self.config.xml_language), program.name, True))
            if program.is_set('originaltitle') and program.is_set('country') :
                xml.append(self.add_starttag('title', 4, 'lang="%s"' % (program.get_value('country').lower()), program.get_value('originaltitle'), True))

            # Subtitle
            if program.is_set('episode title') and program.get_value('episode title') != program.name:
                xml.append(self.add_starttag('sub-title', 4, 'lang="%s"' % (self.config.xml_language), program.get_value('episode title') ,True))

            # Description
            desc_line = program.get_description()
            if desc_line != '':
                xml.append(self.add_starttag('desc', 4, 'lang="%s"' % (self.config.xml_language), desc_line,True))

            # Process credits section if present.
            # This will generate director/actor/presenter info.
            if program.is_set('credits'):
                xml.append(self.add_starttag('credits', 4))
                for role in self.config.key_values['credits']:
                    if program.is_set(role):
                        rlist = program.get_value(role)
                        for name in rlist:
                            if isinstance(name, dict) and 'name'in name:
                                xml.append(self.add_starttag((role), 6, '', self.xmlescape(name['name']),True))

                            elif name != '':
                                xml.append(self.add_starttag((role), 6, '', self.xmlescape(name),True))

                xml.append(self.add_endtag('credits', 4))

            # Original Air-Date
            if program.is_set('airdate'):
                xml.append(self.add_starttag('date', 4, '',  \
                    self.format_timezone(program.get_value('airdate'),True), True))

            elif program.is_set('premiere year'):
                xml.append(self.add_starttag('date', 4, '', program.get_value('premiere year'),True))

            # Genre
            cat = program.get_genre()
            if self.config.channels[chanid].opt_dict['cattrans']:
                xml.append(self.add_starttag('category', 4 , '', cat, True))

            else:
                xml.append(self.add_starttag('category', 4, 'lang="%s"' % (self.config.xml_language), cat, True))

            # An available url
            if program.is_set('infourl'):
                xml.append(self.add_starttag('url', 4, '', program.get_value('infourl'),True))

            # A Country
            if program.is_set('country'):
                xml.append(self.add_starttag('country', 4, '', program.get_value('country').upper(),True))

            # Only add season/episode if relevant. i.e. Season can be 0 if it is a pilot season, but episode never.
            # Also exclude Sports for MythTV will make it into a Series
            if program.is_set('season') and program.is_set('episode') and cat.lower() not in self.config.episode_exclude_genres:
                se = program.get_value('season') -1
                ep = program.get_value('episode') -1
                if se >= 0 and ep >= 0:
                    if program.is_set("episodecount"):
                        ep = '%s/%s' % (ep, program.get_value('episodecount'))

                    if se == 0:
                        text = ' . %s . '  % (ep)

                    else:
                        text = '%s . %s . '  % (se, ep)

                    xml.append(self.add_starttag('episode-num', 4, 'system="xmltv_ns"', text,True))

            # Process video/audio/teletext sections if present
            if program.get_value('widescreen') or program.get_value('blackwhite') \
              or (program.get_value('HD') and (self.config.channels[chanid].opt_dict['mark_hd'] or add_HD == True)):
                xml.append(self.add_starttag('video', 4))

                if program.get_value('widescreen'):
                    xml.append(self.add_starttag('aspect', 6, '', '16:9',True))

                if program.get_value('blackwhite'):
                    xml.append(self.add_starttag('colour', 6, '', 'no',True))

                if program.get_value('HD') and (self.config.channels[chanid].opt_dict['mark_hd'] or add_HD == True):
                    xml.append(self.add_starttag('quality', 6, '', 'HDTV',True))

                xml.append(self.add_endtag('video', 4))

            if program.is_set('audio'):
                xml.append(self.add_starttag('audio', 4))
                xml.append(self.add_starttag('stereo', 6, '',program.get_value('audio') ,True))
                xml.append(self.add_endtag('audio', 4))

            # It's been shown before
            if program.get_value('rerun'):
                xml.append(self.add_starttag('previously-shown', 4, '', '',True))

            # It's a first
            if program.get_value('premiere'):
                xml.append(self.add_starttag('premiere', 4, '', '',True))

            # It's the last showing
            if program.get_value('last-chance'):
                xml.append(self.add_starttag('last-chance', 4, '', '',True))

            # It's new
            if program.get_value('new'):
                xml.append(self.add_starttag('new', 4, '', '',True))

            # There are teletext subtitles
            if program.get_value('teletext'):
                xml.append(self.add_starttag('subtitles', 4, 'type="teletext"', '',True))

            # Add any rating items
            if program.is_set('rating') and self.config.opt_dict['kijkwijzerstijl'] in ('long', 'short', 'single'):
                pr = program.get_value('rating')
                kstring = ''
                # First only one age limit from high to low
                for k in self.config.rating['unique_codes'].keys():
                    if k in pr:
                        if self.config.opt_dict['kijkwijzerstijl'] == 'single':
                            kstring += (self.config.rating['unique_codes'][k]['code'] + ': ')

                        else:
                            xml.append(self.add_starttag('rating', 4, 'system="%s"' % (self.config.rating['name'])))
                            if self.config.opt_dict['kijkwijzerstijl'] == 'long':
                                xml.append(self.add_starttag('value', 6, '', self.config.rating['unique_codes'][k]['text'], True))

                            else:
                                xml.append(self.add_starttag('value', 6, '', self.config.rating['unique_codes'][k]['code'], True))

                            xml.append(self.add_starttag('icon', 6, 'src="%s"' % self.config.rating['unique_codes'][k]['icon'], '', True))
                            xml.append(self.add_endtag('rating', 4))
                        break

                # And only one of any of the others
                for k in self.config.rating['addon_codes'].keys():
                    if k in pr:
                        if self.config.opt_dict['kijkwijzerstijl'] == 'single':
                            kstring += k.upper()

                        else:
                            xml.append(self.add_starttag('rating', 4, 'system="%s"' % (self.config.rating['name'])))
                            if self.config.opt_dict['kijkwijzerstijl'] == 'long':
                                xml.append(self.add_starttag('value', 6, '', self.config.rating['addon_codes'][k]['text'], True))

                            else:
                                xml.append(self.add_starttag('value', 6, '', self.config.rating['addon_codes'][k]['code'], True))

                            xml.append(self.add_starttag('icon', 6, 'src="%s"' % self.config.rating['addon_codes'][k]['icon'], '', True))
                            xml.append(self.add_endtag('rating', 4))

                if self.config.opt_dict['kijkwijzerstijl'] == 'single' and kstring != '':
                    xml.append(self.add_starttag('rating', 4, 'system="%s"' % (self.config.rating['name'])))
                    xml.append(self.add_starttag('value', 6, '', kstring, True))
                    xml.append(self.add_endtag('rating', 4))

            # Set star-rating if applicable
            if program.is_set('star-rating'):
                xml.append(self.add_starttag('star-rating', 4))
                xml.append(self.add_starttag('value', 6, '',('%s/10' % (program.get_value('star-rating'))).strip(),True))
                xml.append(self.add_endtag('star-rating', 4))

            xml.append(self.add_endtag('programme', 2))
            self.xml_programs[xmltvid].append(xml)
            program = program.next

    def get_xmlstring(self):
        '''
        Compound the compleet XML output and return it
        '''
        if self.config.output == None:
            startstring =[u'<?xml version="1.0" encoding="%s"?>\n' % self.config.logging.local_encoding]

        else:
            startstring =[u'<?xml version="1.0" encoding="%s"?>\n' % self.xmlencoding]

        startstring.append(u'<!DOCTYPE tv SYSTEM "xmltv.dtd">\n')
        startstring.append(u'<tv generator-info-name="%s" generator-info-url="https://github.com/tvgrabbers/tvgrabnlpy">\n' % self.config.version(True))
        closestring = u'</tv>\n'

        xml = []
        xml.append(u"".join(startstring))

        for channel in self.config.channels.values():
            if channel.active and channel.xmltvid in self.xml_channels:
                xml.append(u"".join(self.xml_channels[channel.xmltvid]))
                if channel.opt_dict['add_hd_id'] and '%s-hd' % (channel.xmltvid) in self.xml_channels:
                    xml.append(u"".join(self.xml_channels['%s-hd' % channel.xmltvid]))

        for channel in self.config.channels.values():
            if channel.active and channel.xmltvid in self.xml_programs:
                for program in self.xml_programs[channel.xmltvid]:
                    xml.append(u"".join(program))

                if channel.opt_dict['add_hd_id'] and '%s-hd' % (channel.xmltvid) in self.xml_channels:
                    for program in self.xml_programs['%s-hd' % channel.xmltvid]:
                        xml.append(u"".join(program))

        xml.append(closestring)

        return u"".join(xml)

    def print_string(self):
        '''
        Print the compleet XML string to stdout or selected file
        '''
        xml = self.get_xmlstring()

        if xml != None:
            if self.config.output == None:
                sys.stdout.write(xml.encode(self.config.logging.local_encoding, 'replace'))

            else:
                self.config.output.write(xml)

            if self.config.write_info_files:
                self.config.infofiles.write_xmloutput(xml)

# end XMLoutput
