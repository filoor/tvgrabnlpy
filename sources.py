#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Python 3 compatibility
from __future__ import unicode_literals
# from __future__ import print_function

import re, sys, traceback, codecs
import time, datetime, random, difflib
import httplib, json, socket
import timezones,tv_grab_fetch
try:
    import urllib.request as urllib
except ImportError:
    import urllib2 as urllib
try:
    from html.entities import name2codepoint
except ImportError:
    from htmlentitydefs import name2codepoint
from threading import Thread, Lock, Semaphore
from xml.sax import saxutils
from xml.etree import cElementTree as ET
from Queue import Queue, Empty
try:
    unichr(42)
except NameError:
    unichr = chr    # Python 3

CET_CEST = timezones.AmsterdamTimeZone()
UTC  = timezones.UTCTimeZone()

class tvgids_JSON(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the tvgids.nl json pages. Based on FetchData
    """
    def init_channels(self):
        """ Detail Site layout oud
            <head>
            <body>
                <div id="container">
                    <div id="header">
                    <div id="content">
                        <div id="content-header">Title</div>
                        <div id="content-col-left">
                            <div id="prog-content">Description</div>
                        <div id="content-col-right">
                            <div id="prog-info">
                                <div id="prog-info-content">
                                    <ul id="prog-info-content-colleft">
                                        <li><strong>Titel:</strong>Nederland Waterland</li>
                                            ...
                                    <ul id="prog-info-content-colright">
                                        <li><strong>Jaar van premiere:</strong>2014</li>
                                            ...
                                        <li><strong>Bijzonderheden:</strong>Teletekst ondertiteld, Herhaling, HD 1080i</li>
                                <div id="prog-info-footer"></div>
                            </div>
                        </div>
                    </div>
                    <div class="clearer"></div>
                </div>
                <div id="footer-container">
            </body>
            Nieuw
            <head>
            <body>
                <input type="hidden" id="categoryClass" value="">
                    <input type="hidden" id="notAllowedClass" value="">
                        <input type="hidden" id="notAllowedTitles" value="">
                            <div class="container pagecontainer">
                                <div class="row">
                                    <div class="col-md-8">
                                        <div id="prog-content">
                                            <div id="prog-video">
                                            ...
                                            </div>
                                            <div class="programmering">
                                                <h1>Harry Potter and the Goblet of Fire<span><sup>(2005)</sup></span></h1>
                                                <div class="clear:both;"></div>
                                                <script type="text/javascript" src="http://tvgidsassets.nl/v43/js/nlziet.js"></script>
                                                <div class="programmering_details">
                                                    <ul>
                                                        <li class="datum_tijd"> 1 mei 2015, 22:45 - 23:55 uur</li>
                                                        <li class="zender"><img src="http://tvgidsassets.nl/img/channels/53x27/36.png">SBS 6</li>
                                                    </ul>
                                                </div>
                                                <div style="clear:both"></div>
                                            </div>
                                            <div class="clear"></div>
                                                ...
                                            <div class="clear"></div>
                                            <p class="summary">
                                                <span class="articleblock articleblock_color_fantasy">
                                            FANTASY
                                                </span>
                                                                    Harry Potter gaat zijn vierde schooljaar in op de magische school Zweinstein, waar dit jaar het belangrijke internationale Triwizard Tournament wordt gehouden. Deze competitie is alleen voor de oudere en ervaren tovenaarsstudenten, maar toch komt Harry's naam boven als een van de deelnemers. Harry weet niet hoe dit mogelijk is, maar wordt toch gedwongen om mee te doen. Terwijl Harry zich voorbereidt op de gevaarlijke wedstrijd, wordt duidelijk dat de boosaardige Voldemort en zijn aanhangers steeds sterker worden en het nog altijd op zijn leven hebben gemunt. Dit nieuws is niet het enige wat Harry de rillingen bezorgt, hij heeft ook nog geen afspraakje voor het gala.
                                            </p>
                                            <p></p>
                                            <br class="brclear" />
                                            <div class="programmering_info_socials">
                                                ...
                                            </div>
                                            <br class="clear" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </body>
        """

        # These regexes fetch the relevant data out of thetvgids.nl pages, which then will be parsed to the ElementTree
        self.retime = re.compile(r'(\d\d\d\d)-(\d+)-(\d+) (\d+):(\d+)(?::\d+)')
        self.tvgidsnlprog = re.compile('<div id="prog-content">(.*?)<div id="prog-banner-content"',re.DOTALL)
        self.tvgidsnltitle = re.compile('<div class="programmering">(.*?)</h1>',re.DOTALL)
        self.tvgidsnldesc = re.compile('<p(.*?)</p>',re.DOTALL)
        self.tvgidsnldesc2 = re.compile('<div class="tekst col-sm-12">(.*?)</div>',re.DOTALL)
        self.tvgidsnldetails = re.compile('<div class="programmering_info_detail">(.*?)</div>',re.DOTALL)
        self.aflevering = re.compile('(\d*)/?\d*(.*)')

        self.channels = {}
        self.url_channels = ''
        self.cooky_cnt = 0

        self.init_channel_source_ids()
        for channel in self.channels.values():
            if self.url_channels == '':
                self.url_channels = channel

            else:
                self.url_channels  = '%s,%s' % (self.url_channels, channel)

    def get_url(self, type = 'channels', offset = 0, id = None):

        tvgids = 'http://www.tvgids.nl/'
        tvgids_json = tvgids + 'json/lists/'

        if type == 'channels':
            return  u'%schannels.php' % (tvgids_json)

        elif type == 'day':
            return '%sprograms.php?channels=%s&day=%s' % (tvgids_json, self.url_channels, offset)

        elif (id == None) or id == '':
            return ''

        elif type == 'detail':
            return u'%sprogramma/%s/?cookieoptin=true' % (tvgids, id)

        elif type == 'json_detail':
            return u'%sprogram.php?id=%s/' % (tvgids_json, id)

    def match_to_date(self, timestring, time, program):
        match = self.retime.match(self.functions.unescape(timestring))

        if match:
            return datetime.datetime(int(match.group(1)),int(match.group(2)),\
                    int(match.group(3)),int(match.group(4)),int(match.group(5)),
                    tzinfo=CET_CEST)
        else:
            self.config.log("Can not determine %s for %s\n" % (time,program))
            return None

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        # download the json feed
        total = self.config.fetch_func.get_page(self.get_url(), 'utf-8')
        if total == None:
            self.config.log("Unable to get channel info from %s\n" % self.source)
            return 69  # EX_UNAVAILABLE

        channel_list = json.loads(total)

        # and create a file with the channels
        self.all_channels ={}
        for channel in channel_list:
            # the json data has the channel names in XML entities.
            chanid = channel['id']
            self.all_channels[chanid] = {}
            self.all_channels[chanid]['name'] = self.functions.unescape(channel['name']).strip()

    def load_pages(self):

        if self.config.opt_dict['offset'] > 4:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        dl = {}
        dd = {}
        for chanid in self.channels.values():
            dl[chanid] =[]
            dd[chanid] =[]

        first_fetch = True

        for retry in (0, 1):
            for offset in range(self.config.opt_dict['offset'], min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 4)):
                if self.quit:
                    return

                # Check if it is already loaded
                if self.day_loaded[0][offset]:
                    continue

                self.config.log(['\n', 'Now fetching %s channels from tvgids.nl\n' % len(self.channels), \
                    '    (day %s of %s).\n' % (offset, self.config.opt_dict['days'])], 2)

                channel_url = self.get_url('day', offset)

                if not first_fetch:
                    # be nice to tvgids.nl
                    time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
                    first_fetch = false

                # get the raw programming for the day
                strdata = self.config.fetch_func.get_page(channel_url, 'utf-8')
                if strdata == None or strdata.replace('\n','') == '{}':
                    self.config.log("No data on tvgids.nl for day=%d\n" % (offset))
                    self.fail_count += 1
                    continue

                # Just let the json library parse it.
                self.base_count += 1
                for chanid, v in json.loads(strdata).iteritems():
                    # Most channels provide a list of program dicts, some a numbered dict
                    try:
                        if isinstance(v, dict):
                            v=list(v.values())

                        elif not isinstance(v, (list,tuple)):
                            raise TypeError

                    except (TypeError, LookupError):
                        self.config.log("Unsubscriptable content from channel url: %r\n" % channel_url)
                        continue
                    # remove the overlap at daychange and seperate the channels
                    for p in v:
                        if not p in dl[chanid]:
                            dd[chanid].append(p)

                self.day_loaded[0][offset] = True
                for chanid, chan_scid in self.channels.items():
                    if len(dd) > 0:
                        self.day_loaded[chanid][offset] = True
                        dl[chan_scid].extend(dd[chan_scid])
                        dd[chan_scid] =[]

        for chanid, chan_scid in self.channels.items():
            if len(dl[chan_scid]) == 0:
                self.config.channels[chanid].source_data[self.proc_id].set()
                continue

            # item is a dict, like:
            # {
            #  u'db_id': u'12379780',
            #  u'titel': u'Der unauff\xe4llige Mr. Crane'
            #  u'genre': u'Film',
            #  u'soort': u'Zwarte komedie',
            #  u'kijkwijzer': u'',
            #  u'artikel_id': None,
            #  u'artikel_titel': None,
            #  u'artikel_tekst': None,
            #  u'artikel_foto': None,
            #  u'datum_start': u'2012-03-12 01:20:00',
            #  u'datum_end': u'2012-03-12 03:05:00',
            # }

            # parse the list to adjust to what we want
            for item in dl[chan_scid]:
                tdict = self.functions.checkout_program_dict()
                if (item['db_id'] != '') and (item['db_id'] != None):
                    tdict['prog_ID'][self.proc_id] = u'nl-%s' % (item['db_id'])
                    self.json_by_id[tdict['prog_ID'][self.proc_id]] = item
                    tdict['ID'] = tdict['prog_ID'][self.proc_id]

                tdict['source'] = self.source
                tdict['channelid'] = chanid
                tdict['channel']  = self.config.channels[chanid].chan_name
                tdict['detail_url'][self.proc_id] = self.get_url(type= 'detail', id = item['db_id'])

                # The Title
                tdict['name'] = self.functions.unescape(item['titel'])
                tdict = self.check_title_name(tdict)
                if  tdict['name'] == None or tdict['name'] == '':
                    self.config.log('Can not determine program title for "%s"\n' % tdict['detail_url'][self.proc_id])
                    continue

                # The timing
                tdict['start-time'] = self.match_to_date(item['datum_start'],"begintijd", tdict['name'])
                tdict['stop-time']  = self.match_to_date(item['datum_end'], "eindtijd", tdict['name'])
                if tdict['start-time'] == None or tdict['stop-time'] == None:
                    continue

                tdict['offset'] = self.functions.get_offset(tdict['start-time'])

                tdict['genre'] = self.functions.unescape(item['genre']) if ('genre' in item and item['genre'] != None) else ''
                tdict['subgenre'] = self.functions.unescape(item['soort']) if ('soort' in item and item['soort'] != None) else ''
                if  ('kijkwijzer' in item and not (item['kijkwijzer'] == None or item['kijkwijzer'] == '')):
                    for k in item['kijkwijzer']:
                        if k in self.config.kijkwijzer.keys() and k not in tdict['kijkwijzer']:
                            tdict['kijkwijzer'].append(k)

                self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict
                with self.source_lock:
                    self.program_data[chanid].append(tdict)

                self.config.genre_list.append((tdict['genre'].lower(), tdict['subgenre'].lower()))

            self.program_data[chanid].sort(key=lambda program: (program['start-time'],program['stop-time']))
            self.parse_programs(chanid, 0, 'None')
            self.channel_loaded[chanid] = True
            self.config.channels[chanid].source_data[self.proc_id].set()
            try:
                self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

            except:
                pass

    def load_detailpage(self, tdict):

        try:
            strdata = self.config.fetch_func.get_page(tdict['detail_url'][self.proc_id])
            if strdata == None:
                self.config.log('Page %s returned no data\n' % (tdict['detail_url'][self.proc_id]), 1)
                return

            if re.search('<div class="cookie-backdrop">', strdata):
                self.cooky_cnt += 1
                if self.cooky_cnt > 2:
                    self.cookyblock = True
                    self.config.log('More then 2 sequential Cooky block pages encountered. Falling back to json\n', 1)

                else:
                    self.cooky_cnt = 0

                return

            strdata = self.tvgidsnlprog.search(strdata)
            if strdata == None:
                self.config.log('Page %s returned no data\n' % (tdict['detail_url'][self.proc_id]), 1)
                return

            strdata = '<div>\n' +  strdata.group(1)
            if re.search('[Gg]een detailgegevens be(?:kend|schikbaar)', strdata):
                strtitle = ''
                strdesc = ''

            else:
                # They sometimes forget to close a <p> tag
                strdata = re.sub('<p>', '</p>xxx<p>', strdata, flags = re.DOTALL)
                strtitle = self.tvgidsnltitle.search(strdata)
                if strtitle == None:
                    strtitle = ''

                else:
                    # There are titles containing '<' (eg. MTV<3) which interfere. Since whe don't need it we remove the title
                    strtitle = re.sub('<h1>.*?<span>', '<h1><span>', strtitle.group(0), flags = re.DOTALL)
                    strtitle = strtitle + '\n</div>\n'

                strdesc = ''
                for d in self.tvgidsnldesc.findall(strdata):
                    strdesc += '<p%s</p>\n' % d

                strdesc = '<div>\n' + strdesc + '\n</div>\n'

                d = self.tvgidsnldesc2.search(strdata)
                if d != None:
                    d = re.sub('</p>xxx<p>', '<p>', d.group(0), flags = re.DOTALL)
                    strdesc += d + '\n'

            strdetails = self.tvgidsnldetails.search(strdata)
            if strdetails == None:
                strdetails = ''

            else:
                strdetails = strdetails.group(0)

            strdata = (self.functions.clean_html('<root>\n' + strtitle + strdesc + strdetails + '\n</root>\n')).strip().encode('utf-8')
            htmldata = ET.fromstring(strdata)

        except:
            self.config.log(['Fetching page %s returned an error:\n' % (tdict['detail_url'][self.proc_id]), traceback.format_exc()])
            if self.config.write_info_files:
                self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                self.config.infofiles.write_raw_string('<root>\n' + strtitle + strdesc + strdetails + '\n</root>\n')

            # if we cannot find the description page,
            # go to next in the loop
            return None

        # We scan every alinea of the description
        try:
            tdict = self.filter_description(htmldata, 'div/p', tdict)
            if self.config.channels[tdict['channelid']].opt_dict['prefered_description'] == self.proc_id:
                tdict['prefered description'] = tdict['description']

        except:
            self.config.log(['Error processing the description from: %s\n' % (tdict['detail_url'][self.proc_id]), traceback.format_exc()])
            if self.config.write_info_files:
                self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                self.config.infofiles.write_raw_string('<root>\n' + strdesc + '\n</root>\n')

        try:
            if htmldata.find('div/h1/span/sup') != None:
                tmp = htmldata.find('div/h1/span/sup').text
                if tmp != None:
                    tmp = re.sub('\(', '', tmp)
                    tdict['jaar van premiere'] = re.sub('\)', '', tmp).strip()

        except:
            self.config.log(traceback.format_exc())
            if self.config.write_info_files:
                self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                self.config.infofiles.write_raw_string(strdata)

        # We scan all the details
        for d in htmldata.findall('div/ul/li'):
            try:
                ctype = self.functions.empersant(d.find('span[@class="col-lg-3"]').text).strip().lower()
                if ctype[-1] == ':':
                    ctype = ctype[0:len(ctype)-1]

                if ctype == 'kijkwijzer':
                    content = ''
                    for k in d.find('span[@class="col-lg-9 programma_detail_info kijkwijzer_img"]'):
                        item = {'text':k.get('alt', '') ,'icon':k.get('src', '')}
                        if item['text'] != '' or item['icon'] != '':
                            for kk, kw in self.config.kijkwijzer.items():
                                if (kw['text'] == item['text'] or kw['icon'] == item['icon']) and kk not in tdict['kijkwijzer']:
                                    tdict['kijkwijzer'].append(kk)
                                    break

                else:
                    content = self.functions.empersant(d.find('span[@class="col-lg-9 programma_detail_info"]').text).strip()

            except:
                self.config.log(traceback.format_exc())
                if self.config.write_info_files:
                    self.config.infofiles.write_raw_string('Error: %s at line %s\n%s\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno, d))
                    self.config.infofiles.write_raw_string(strdata)

                continue

            try:
                if content == '':
                    continue

                elif ctype == 'aflevering':
                    # This contains a subtitle, optionally preseded by an episode number and an episode count
                    txt = self.aflevering.search(content)
                    if txt != None:
                        tdict['episode'] = 0 if txt.group(1) in ('', None) else int(txt.group(1))
                        tdict['titel aflevering'] = '' if txt.group(2) in ('', None) else txt.group(2).strip()

                elif ctype == 'seizoen':
                    try:
                        tdict['season'] = int(content)

                    except:
                        pass

                elif ctype == 'genre':
                    tdict['genre'] = content.title()

                # Parse persons and their roles for credit info
                elif ctype in self.config.roletrans:
                    if not self.config.roletrans[ctype] in tdict['credits']:
                        tdict['credits'][config.roletrans[ctype]] = []

                    content = re.sub(' en ', ' , ', content)
                    persons = content.split(',');
                    for name in persons:
                        if name.find(':') != -1:
                            name = name.split(':')[1]

                        if name.find('-') != -1:
                            name = name.split('-')[0]

                        if name.find('e.a') != -1:
                            name = name.split('e.a')[0]

                        if not self.functions.unescape(name.strip()) in tdict['credits'][config.roletrans[ctype]]:
                            tdict['credits'][config.roletrans[ctype]].append(self.functions.unescape(name.strip()))

                # Add extra properties, while at the same time checking if we do not uncheck already set properties
                elif ctype == 'kleur':
                    tdict['video']['blackwhite'] = (content.find('zwart/wit') != -1)

                elif ctype == 'bijzonderheden':
                    if self.config.write_info_files:
                        self.config.infofiles.addto_detail_list(unicode(ctype + ' = ' + content))

                    content = content.lower()
                    if tdict['video']['breedbeeld'] == False:
                        tdict['video']['breedbeeld'] = (content.find('breedbeeld') != -1)
                    if tdict['video']['HD'] == False:
                        tdict['video']['HD'] = (content.find('hd 1080i') != -1)
                    if tdict['video']['blackwhite'] == False:
                        tdict['video']['blackwhite'] = (content.find('zwart/wit') != -1)
                    if tdict['teletekst'] == False:
                        tdict['teletekst'] = (content.find('teletekst') != -1)
                    if content.find('stereo') != -1: tdict['audio'] = 'stereo'
                    if tdict['rerun'] == False:
                        tdict['rerun'] = (content.find('herhaling') != -1)

                elif ctype == 'nl-url':
                    tdict['infourl'] = content

                elif (ctype not in tdict) and (ctype.lower() not in ('zender', 'datum', 'uitzendtijd', 'titel', 'prijzen')):
                    # In unmatched cases, we still add the parsed type and content to the program details.
                    # Some of these will lead to xmltv output during the xmlefy_programs step
                    if self.config.write_info_files:
                        self.config.infofiles.addto_detail_list(unicode('new tvgids.nl detail => ' + ctype + ': ' + content))

                    tdict[ctype] = content

            except:
                self.config.log(traceback.format_exc())
                if self.config.write_info_files:
                    self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                    self.config.infofiles.write_raw_string(strdata)

        tdict['ID'] = tdict['prog_ID'][self.proc_id]
        tdict[self.detail_check] = True
        return tdict

    def load_json_detailpage(self, tdict):
        try:
            # We first get the json url
            url = 'http://www.tvgids.nl/json/lists/program.php?id=%s' % tdict['prog_ID'][self.proc_id][3:]
            strdata = self.config.fetch_func.get_page(url, 'utf-8')
            if strdata == None or strdata.replace('\n','') == '{}':
                return None

            detail_data = json.loads(strdata)

        except:
            # if we cannot find the description page,
            # go to next in the loop
            return None

        for ctype, content in detail_data.items():
            if ctype in ('db_id', 'titel', 'datum', 'btijd', 'etijd', 'zender_id'):
                # We allready have these or we don use them
                continue

            if content == '':
                continue

            if ctype == 'genre':
                tdict['genre'] = content

            elif  ctype == 'kijkwijzer':
                for k in content:
                    if k in self.config.kijkwijzer.keys() and k not in tdict['kijkwijzer']:
                        tdict['kijkwijzer'].append(k)

            elif ctype == 'synop':
                content = re.sub('<p>', '', content)
                content = re.sub('</p>', '', content)
                content = re.sub('<br/>', '', content)
                content = re.sub('<strong>.*?</strong>', '', content)
                content = re.sub('<.*?>', '', content)
                content = re.sub('\\r\\n', '\\n', content)
                content = re.sub('\\n\\n\\n', '\\n', content)
                content = re.sub('\\n\\n', '\\n', content)
                if tdict['subgenre'].lower().strip() == content[0:len(tdict['subgenre'])].lower().strip():
                    content = content[len(tdict['subgenre'])+1:]

                if content > tdict['description']:
                    tdict['description'] = self.functions.unescape(content)

                if self.config.channels[tdict['channelid']].opt_dict['prefered_description'] == self.proc_id:
                    tdict['prefered description'] = tdict['description']

            # Parse persons and their roles for credit info
            elif ctype in self.config.roletrans:
                if not self.config.roletrans[ctype] in tdict['credits']:
                    tdict['credits'][config.roletrans[ctype]] = []
                persons = content.split(',');
                for name in persons:
                    if name.find(':') != -1:
                        name = name.split(':')[1]

                    if name.find('-') != -1:
                        name = name.split('-')[0]

                    if name.find('e.a') != -1:
                        name = name.split('e.a')[0]

                    if not self.functions.unescape(name.strip()) in tdict['credits'][config.roletrans[ctype]]:
                        tdict['credits'][config.roletrans[ctype]].append(self.functions.unescape(name.strip()))

            else:
                if self.config.write_info_files:
                    self.config.infofiles.addto_detail_list(unicode('new tvgids.nl json detail => ' + ctype + ': ' + content))

        tdict['ID'] = tdict['prog_ID'][self.proc_id]
        tdict[self.detail_check] = True
        return tdict

# end tvgids_JSON

class tvgidstv_HTML(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the tvgids.tv page. Based on FetchData Class
    """
    def init_channels(self):
        """ General Site layout
            <head>
            <body><div id="wrap"><div class="container"><div class="row">
                            <div class="span16">
                            <div class="span47 offset1">
                                een of meer
                                <div class="section">
                                    ...
                            <div class="span30 offset1">
                <div id="footer">

        Channel listing:
            <div class="section-title">
                contains the grouping name (Nederlands, Vlaams, ...)
            </div>
            <div class="section-content"><div class="section-item channels"><div class="section-item-content">
                        each contain groupings of up to four channels
                        <a href="/zenders/nederland-1" title="TV Gids NPO 1" class="">
                            <div class="channel-icon sprite-channel-1"></div><br />
                           <div class="channel-name ellipsis">NPO 1</div>
                        </a>
            </div></div></div>

        Program listing:
            <div class="section-content">
                contains for each program
                <a href="/tv/hart-van-nederland" title="Hart van Nederland"></a>
                <a href="/tv/hart-van-nederland/12568262" title="Hart van Nederland" class="section-item posible-progress-bar" rel="nofollow">
                    <div class="content">
                        <div class="channel-icon sprite-channel-8"></div>
                        <span class="section-item-title">
                                                                05:25
                                                                Hart van Nederland
                        </span>
                        <div class="clearfix"></div>
                    </div>
                </a>
            </div>

        Detail layout
            <div class="section-title">
                <h1>Navy NCIS</h1>
                <a class="channel-icon sprite-channel-8 pull-right" href="/zenders/net-5" title="TV Gids NET 5"></a>
            </div>
            <div class="section-content">
                <div class="section-item gray">
                    <img class="pull-right large" src="http://images.cdn.tvgids.tv/programma/square_iphone_hd_TVGiDStv_navy-ncis.jpg" alt="Navy NCIS" title="Navy NCIS" />
                    <dl class="dl-horizontal program-details">
                        <dt>Datum</dt><dd>Ma 29 december 2014 </dd>
                        <dt>Tijd</dt><dd>19:35 tot 20:30</dd>
                        <dt>    Name    </dt><dd>    Content    </dd>
                                   ...
                    </dl>
                    <div class="program-details-social">
                        ...
                    </div>
                    <p>                description                     </p>
                </div>
            </div>
        """

        # These regexes are used to get the time offset (whiche day they see as today)
        self.fetch_datecontent = re.compile('<div class="section-title select-scope">(.*?)<div class="section-content">',re.DOTALL)
        # These regexes fetch the relevant data out of thetvgids.tv pages, which then will be parsed to the ElementTree
        self.getcontent = re.compile('<div class="span47 offset1">(.*?)<div class="span30 offset1">',re.DOTALL)
        self.daydata = re.compile('<div class="section-content">(.*?)<div class="advertisement">',re.DOTALL)
        self.detaildata = re.compile('<div class="section-title">(.*?)<div class="advertisement">',re.DOTALL)

        self.init_channel_source_ids()

    def get_url(self, channel = None, offset = 0, href = None):

        tvgidstv_url = 'http://www.tvgids.tv'

        if href == None and channel == None:
            return u'%s/zenders/' % tvgidstv_url

        if href == None:
            return u'%s/zenders/%s/%s' % (tvgidstv_url, channel, offset)

        if href == '':
            return ''

        else:
            return u'%s%s' % (tvgidstv_url, self.functions.unescape(href))

    def check_date(self, page_data, channel, offset):

        # Check on the right offset for appending the date to the time. Their date switch is aroud 6:00
        dnow = datetime.datetime.now(CET_CEST).strftime('%d %b').split()
        dlast = datetime.date.fromordinal(self.current_date - 1).strftime('%d %b').split()

        if page_data == None:
            self.config.log("Skip channel=%s on tvgids.tv!, day=%d. No data\n" % (channel, offset))
            return None

        d = self.fetch_datecontent.search(page_data)
        if d == None:
            self.config.log('Unable to veryfy the right offset on .\n' )
            return None

        try:
            d = d.group(1)
            d = self.functions.clean_html(d)
            htmldata = ET.fromstring( ('<div>' + d).encode('utf-8'))

        except:
            self.config.log('Unable to veryfy the right offset on .\n' )
            return None

        dd = htmldata.find('div/a[@class="today "]/br')
        if dd == None:
            dd = htmldata.find('div/a[@class="today"]/br')

        if dd == None:
            dd = htmldata.find('div/a[@class="today active"]/br')

        if dd.tail == None:
            self.config.log('Unable to veryfy the right offset on .\n' )
            return None

        d = dd.tail.strip().split()
        if int(dnow[0]) == int(d[0]):
            return offset

        elif int(dlast[0]) == int(d[0]):
            return offset - 1

        else:
            self.config.log("Skip channel=%s, day=%d. Wrong date!\n" % (channel, offset))
            return None

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        try:
            strdata = self.config.fetch_func.get_page(self.get_url())
            if strdata == None:
                self.fail_count += 1
                return

            strdata = self.functions.clean_html('<div>' + self.getcontent.search(strdata).group(1)).encode('utf-8')
            htmldata = ET.fromstring(strdata)

        except:
            self.fail_count += 1
            self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
            return 69  # EX_UNAVAILABLE

        self.all_channels ={}
        for changroup in htmldata.findall('div[@class="section"]'):
            group_name = self.functions.empersant(changroup.findtext('div[@class="section-title"]')).strip()
            for chan in changroup.findall('div[@class="section-content"]/div[@class="section-item channels"]/div[@class="section-item-content"]/a'):
                chanid = chan.get('href')
                if chanid == None:
                    continue

                chanid = re.split('/', chanid)[2]
                name = self.functions.empersant(chan.findtext('div[@class="channel-name ellipsis"]'))
                self.all_channels[chanid] = {}
                self.all_channels[chanid]['name'] = name
                self.all_channels[chanid]['group'] = 99
                for id in self.config.group_order:
                    if group_name == self.config.chan_groups[id]:
                        self.all_channels[chanid]['group'] = id
                        break

    def match_genre(self, dtext, tdict):
        if len(dtext) > 20:
            tdict['genre'] = u'overige'
            return tdict

        if dtext.lower() in self.config.source_cattrans[self.proc_id].keys():
            tdict['genre'] = self.config.source_cattrans[self.proc_id][dtext.lower()].capitalize()
            tdict['subgenre'] = dtext

        # Now we try to match the genres not found in source_cattrans[self.proc_id]
        else:
            if 'jeugd' in dtext.lower():
                tdict['genre'] = u'Jeugd'

            elif 'muziek' in dtext.lower():
                tdict['genre'] = u'Muziek'

            elif 'sport' in dtext.lower():
                tdict['genre'] = u'Sport'

            elif 'nieuws' in dtext.lower():
                tdict['genre'] = u'Nieuws/Actualiteiten'

            elif 'natuur' in dtext.lower():
                tdict['genre'] = u'Natuur'

            elif 'cultuur' in dtext.lower():
                tdict['genre'] = u'Kunst en Cultuur'

            elif 'kunst' in dtext.lower():
                tdict['genre'] = u'Kunst en Cultuur'

            elif 'wetenschap' in dtext.lower():
                tdict['genre'] = u'Wetenschap'

            elif 'medisch' in dtext.lower():
                tdict['genre'] = u'Wetenschap'

            elif 'film' in dtext.lower():
                tdict['genre'] = u'Film'

            elif 'spel' in dtext.lower():
                tdict['genre'] = u'Amusement'

            elif 'show' in dtext.lower():
                tdict['genre'] = u'Amusement'

            elif 'quiz' in dtext.lower():
                tdict['genre'] = u'Amusement'

            elif 'praatprogramma' in dtext.lower():
                tdict['genre'] = u'Magazine'

            elif 'magazine' in dtext.lower():
                tdict['genre'] = u'Magazine'

            elif 'documentair' in dtext.lower():
                tdict['genre'] = u'Informatief'

            elif 'serie' in dtext.lower():
                tdict['genre'] = u'Serie/Soap'

            elif 'soap' in dtext.lower():
                tdict['genre'] = u'Serie/Soap'

            elif 'drama' in dtext.lower():
                tdict['genre'] = u'Serie/Soap'

            elif 'thriller' in dtext.lower():
                tdict['genre'] = u'Serie/Soap'

            elif 'komedie' in dtext.lower():
                tdict['genre'] = u'Serie/Soap'

            elif 'western' in dtext.lower():
                tdict['genre'] = u'Serie/Soap'

            else:
                tdict['genre'] = u'overige'
                if self.config.write_info_files and not tdict['channelid'] in ('29', '438',):
                    self.config.infofiles.addto_detail_list(unicode('unknown tvgids.tv genre => ' + dtext + ' on ' + tdict['channel']))

            if not tdict['channelid'] in ('29', '438',):
                tdict['subgenre'] = dtext
                # And add them to source_cattrans[self.proc_id] (and tv_grab_nl_py.set for later reference
                # But not for Discovery Channel or TLC as that is garbage
                if not tdict['genre'] == u'overige':
                    self.config.new_cattrans[self.proc_id].append((dtext.lower().strip(), tdict['genre']))

        return tdict

    def load_pages(self):
        first_fetch = True
        try:
            for retry in (0, 1):
                channel_cnt = 0
                for chanid in self.channels.keys():
                    channel_cnt += 1
                    failure_count = 0
                    if self.quit:
                        return

                    if self.config.channels[chanid].source_data[self.proc_id].is_set():
                        continue

                    channel = self.channels[chanid]
                    # Start from the offset but skip the days allready fetched by tvgids.nl
                    # Except when append_tvgidstv is False
                    if self.config.channels[chanid].opt_dict['append_tvgidstv']:
                        fetch_range = []
                        for i in range( self.config.opt_dict['offset'], (self.config.opt_dict['offset'] + self.config.opt_dict['days'])):
                            if not chanid in self.config.channelsource[0].day_loaded or not self.config.channelsource[0].day_loaded[chanid][i]:
                                fetch_range.append(i)

                    else:
                        fetch_range = range( self.config.opt_dict['offset'], (self.config.opt_dict['offset'] + self.config.opt_dict['days']))

                    if len(fetch_range) == 0:
                        self.config.channels[chanid].source_data[self.proc_id].set()
                        continue

                    # Tvgids.tv shows programs per channel per day, so we loop over the number of days
                    # we are required to grab
                    for offset in fetch_range:
                        # Check if it is allready loaded
                        if self.day_loaded[chanid][offset] != False or \
                          (self.config.channels[chanid].opt_dict['append_tvgidstv'] and \
                          chanid in self.config.channelsource[0].day_loaded and \
                          self.config.channelsource[0].day_loaded[chanid][offset]):
                            continue

                        self.config.log(['\n', 'Now fetching %s(xmltvid=%s%s) from tvgids.tv\n' % \
                            (self.config.channels[chanid].chan_name, self.config.channels[chanid].xmltvid , (self.config.channels[chanid].opt_dict['compat'] and '.tvgids.nl' or '')), \
                            '    (channel %s of %s) for day %s of %s.\n' % \
                            (channel_cnt, len(self.channels), offset, self.config.opt_dict['days'])], 2)
                        if not first_fetch:
                            # be nice to tvgids.tv
                            time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
                            first_fetch = false

                        # get the raw programming for the day
                        try:
                            channel_url = self.get_url(channel, offset)
                            strdata = self.config.fetch_func.get_page(channel_url)

                            if strdata == None:
                                self.config.log("Skip channel=%s on tvgids.tv, day=%d. No data!\n" % (self.config.channels[chanid].chan_name, offset))
                                failure_count += 1
                                self.fail_count += 1
                                continue

                        except:
                            self.config.log('Error: "%s" reading the tvgids.tv basepage for channel=%s, day=%d.\n' %
                                (sys.exc_info()[1], self.config.channels[chanid].chan_name, offset))
                            failure_count += 1
                            self.fail_count += 1
                            continue


                        # Check on the right offset for appending the date to the time. Their date switch is aroud 6:00
                        x = self.check_date(strdata, self.config.channels[chanid].chan_name, offset)
                        if x == None:
                            self.config.log("Skip channel=%s on tvgids,tv, day=%d. Wrong date!\n" % (self.config.channels[chanid].chan_name, offset))
                            failure_count += 1
                            self.fail_count += 1
                            continue

                        date_offset = x
                        scan_date = datetime.date.fromordinal(self.current_date + date_offset)
                        last_program = datetime.datetime.combine(datetime.date.fromordinal(self.current_date + date_offset - 1), datetime.time(0, 0, 0 ,0 ,CET_CEST))

                        # and extract the ElementTree
                        try:
                            strdata =self.daydata.search(strdata).group(1)
                            strdata = self.functions.clean_html(strdata)
                            htmldata = ET.fromstring( ('<div><div>' + strdata).encode('utf-8'))

                        except:
                            self.config.log(["Error extracting ElementTree for channel:%s day:%s on tvgids.tv\n" % \
                                (self.config.channels[chanid].chan_name, offset), \
                                "Possibly an incomplete pagefetch. Retry in the early morning after 4/5 o'clock.\n"])

                            if self.config.write_info_files:
                                self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                                self.config.infofiles.write_raw_string(u'<div><div>' + strdata + u'\n')

                            failure_count += 1
                            self.fail_count += 1
                            self.day_loaded[chanid][offset] = None
                            continue

                        try:
                            if htmldata.find('div/a[@class]') == None:
                                self.config.log(["No Programming for channel=%s, day=%d on tvgids.tv!\n" % (self.config.channels[chanid].chan_name, offset), \
                                        "   We assume further pages to be empty!\n"])

                                for d in range((offset - 1), self.config.opt_dict['days']):
                                    self.day_loaded[chanid][d] = None

                                continue

                            for p in htmldata.findall('div/a[@class]'):
                                tdict = self.functions.checkout_program_dict()
                                tdict['source'] = u'tvgidstv'
                                tdict['channelid'] = chanid
                                tdict['channel'] = self.config.channels[chanid].chan_name
                                tdict['detail_url'][self.proc_id] = self.get_url(href = p.get('href'))
                                tdict['prog_ID'][self.proc_id] = u'tv-%s' % tdict['detail_url'][self.proc_id].split('/')[5]  if (tdict['detail_url'][self.proc_id] != '') else ''

                                # The Title
                                tdict['name'] = self.functions.empersant(p.get('title'))
                                tdict = self.check_title_name(tdict)
                                if  tdict['name'] == None or tdict['name'] == '':
                                    self.config.log('Can not determine program title for "%s"\n' % tdict['detail_url'][self.proc_id])
                                    continue

                                # Get the starttime and make sure the midnight date change is properly crossed
                                start = p.findtext('div[@class="content"]/span[@class="section-item-title"]').split()[0]
                                if start == None or start == '':
                                    self.config.log('Can not determine starttime for "%s"\n' % tdict['name'])
                                    continue

                                prog_time = datetime.time(int(start.split(':')[0]), int(start.split(':')[1]), 0 ,0 ,CET_CEST)
                                if datetime.datetime.combine(scan_date, prog_time) < last_program:
                                    date_offset = date_offset +1
                                    scan_date = datetime.date.fromordinal(self.current_date + date_offset)

                                tdict['offset'] = date_offset
                                tdict['start-time'] = datetime.datetime.combine(scan_date, prog_time)
                                last_program = tdict['start-time']

                                m = p.findtext('div[@class="content"]/span[@class="label"]')
                                # span = "IMDB * n.n"
                                if m != None:
                                    dd = unicode(m.split(':')[1])
                                    if dd != '':
                                        tdict['star-rating'] = dd

                                d = p.findtext('div[@class="content"]/p')
                                # p      = "dd/mm - IMDB * n.n - <genre>, beschrijving"
                                if d != None:
                                    dd = d.split(',')
                                    tdict['description'] = self.functions.empersant(d[len(dd[0])+1:]).strip()
                                    dd = self.functions.empersant(dd[0]).split('-')
                                    tdict = self.match_genre(self.functions.empersant(unicode(dd[-1])), tdict)

                                    if tdict['star-rating'] == '' and len(dd) > 1:
                                        ddd = dd[-2].split('*')
                                        if ddd[0].strip() == 'IMDB':
                                            tdict['star-rating'] = unicode(ddd[1].strip())

                                # and append the program to the list of programs
                                with self.source_lock:
                                    self.program_data[chanid].append(tdict)

                        except:
                            self.config.log(['Error processing tvgids.tv data for channel:%s day:%s\n' % \
                                (self.config.channels[chanid].chan_name, offset), traceback.format_exc()])
                            self.fail_count += 1
                            continue

                        self.base_count += 1
                        self.day_loaded[chanid][offset] = True

                    if len(self.program_data[chanid]) == 0:
                        self.config.channels[chanid].source_data[self.proc_id].set()
                        continue

                    # Add starttime of the next program as the endtime
                    with self.source_lock:
                        self.program_data[chanid].sort(key=lambda program: (program['start-time']))
                        self.add_endtimes(chanid, 6)

                        for tdict in self.program_data[chanid]:
                            self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

                    if failure_count == 0 or retry == 1:
                        self.channel_loaded[chanid] = True
                        self.parse_programs(chanid, 0, 'None')
                        self.config.channels[chanid].source_data[self.proc_id].set()

                        try:
                            self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                        except:
                            pass

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread:\n' %  (self.source), traceback.format_exc()], 0)
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

    def load_detailpage(self, tdict):

        try:
            strdata = self.config.fetch_func.get_page(tdict['detail_url'][self.proc_id])
            if strdata == None:
                return

            strdata = self.functions.clean_html('<root><div><div class="section-title">' + self.detaildata.search(strdata).group(1) + '</root>').encode('utf-8')
        except:
            self.config.log(['Error Fetching detailpage %s\n' % tdict['detail_url'][self.proc_id], traceback.format_exc()])
            return None

        try:
            htmldata = ET.fromstring(strdata)

        except:
            self.config.log("Error extracting ElementTree from:%s on tvgids.tv\n" % (tdict['detail_url'][self.proc_id]))
            if self.config.write_info_files:
                self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                self.config.infofiles.write_raw_string(strdata + u'\n')

            return None

        # We scan every alinea of the description
        try:
            tdict = self.filter_description(htmldata, 'div/div/div/p', tdict)
            if self.config.channels[tdict['channelid']].opt_dict['prefered_description'] == self.proc_id:
                tdict['prefered description'] = tdict['description']

        except:
            self.config.log(['Error processing the description from: %s\n' % (tdict['detail_url'][self.proc_id]), traceback.format_exc()])

        data = htmldata.find('div/div[@class="section-content"]')
        datatype = u''
        try:
            for d in data.find('div/dl'):
                if d.tag == 'dt':
                    datatype = self.functions.empersant(d.text.lower())

                elif d.tag == 'dd':
                    dtext = self.functions.empersant(d.text).strip() if (d.text != None) else ''
                    if datatype in ('datum', 'tijd', 'uitzending gemist', 'officiële twitter', 'twitter hashtag', 'deel-url'):
                        continue

                    elif datatype == 'genre':
                        if dtext == '':
                            continue

                        tdict = self.match_genre(dtext, tdict)

                    elif datatype == 'jaar':
                        tdict['jaar van premiere'] = dtext

                    elif datatype in self.config.roletrans:
                        tdict['credits'][config.roletrans[datatype]] = []
                        persons = dtext.split(',');
                        for name in persons:
                            if name.find(':') != -1:
                                name = name.split(':')[1]

                            if name.find('-') != -1:
                                name = name.split('-')[0]

                            if name.find('e.a') != -1:
                                name = name.split('e.a')[0]

                            tdict['credits'][config.roletrans[datatype]].append(name.strip())

                    elif datatype == 'imdb':
                        dd = d.find('a')
                        if dd == None:
                            continue

                        durl = self.functions.empersant(dd.get('href', ''))
                        if durl != '':
                            tdict['infourl'] = durl

                        stars = unicode(dd.text.strip())
                        if stars != '' and tdict['star-rating'] == '':
                            tdict['star-rating'] = stars

                    elif datatype== 'officiële website':
                        if d.find('a') == None:
                            continue

                        durl = self.functions.empersant(d.find('a').get('href', ''))
                        if durl != '':
                            tdict['infourl'] = durl

                    elif datatype== 'kijkwijzer':
                        kw_val = d.find('div')
                        if kw_val != None:
                            kw_val = kw_val.get('class').strip()

                        if kw_val != None and len(kw_val) > 27:
                            kw_val = kw_val[27:]
                            if kw_val in self.config.tvkijkwijzer.keys():
                                if self.config.tvkijkwijzer[kw_val] not in tdict['kijkwijzer']:
                                    tdict['kijkwijzer'].append(self.config.tvkijkwijzer[kw_val])

                            elif self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(unicode('new tvgids.tv kijkwijzer detail => ' + datatype + '=' + kw_val))

                    else:
                        if dtext != '':
                            if self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(unicode('new tvgids.tv text detail => ' + datatype + '=' + dtext))

                            tdict[datatype] = dtext

                        elif d.find('div') != None and d.find('div').get('class') != None:
                            if self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(unicode('new tvgids.tv div-class detail => ' + datatype + '=' + d.find('div').get('class')))

                            tdict[datatype] = unicode(d.find('div').get('class'))

                        elif d.find('a') != None and d.find('a').get('href') != None:
                            if self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(unicode('new tvgids.tv a-href detail => ' + datatype + '=' + d.find('a').get('href')))

                            tdict[datatype] = unicode(d.find('a').get('href'))

                        elif self.config.write_info_files:
                            self.config.infofiles.addto_detail_list(unicode('new tvgids.tv empty detail => ' + datatype))

                elif self.config.write_info_files:
                    self.config.infofiles.addto_detail_list(unicode('new tvgids.d-tag => ' + d.tag))

        except:
            self.config.log(['Error processing tvgids.tv detailpage:%s\n' % (tdict['detail_url'][self.proc_id]), traceback.format_exc()])
            return

        tdict['ID'] = tdict['prog_ID'][self.proc_id]
        tdict[self.detail_check] = True

        return tdict

# end tvgidstv_HTML

class rtl_JSON(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the rtl.nl json page. Based on FetchData
    """
    def init_channels(self):
        """ json Layout
            {
            "schedule": [
                {"abstract_key":"       ","season_key":"        ","episode_key":"       ","station":"   ","rerun":false,"unixtime":1421278680}, ...
            ],
            "library": [{
                "abstracts": [
                    {"abstract_key":"   ","name":"Up All Night"}, ...
                ],
                "seasons": [
                    {"season_key":"273426","season_number":"1","name":"Seizoen 1"}, ...
                ],
                "episodes": [
                    {"episode_key":"    ","episode_number":"10","name":"Week off","nicam":"ALt","synopsis":"                    ."}, ...
                ]}
            ]}
        """

        self.page_loaded = False
        self.schedule = {}

        self.init_channel_source_ids()
        for sourceid in self.channels.values():
            self.schedule[sourceid] =[]

    def init_json(self):

        self.json_by_id = {}
        self.jsondata = {}
        self.jsondict = {}
        self.jsondict['abstracts'] = {}
        self.jsondict['seasons'] = {}
        self.jsondict['episodes'] = {}
        self.jsondata = {'abstract_name': {'listname':'abstracts','keyname':'abstract_key','valuename':'name'}, \
                                   'season':                {'listname':'seasons','keyname':'season_key','valuename':'season_number'}, \
                                   'season_name':      {'listname':'seasons','keyname':'season_key','valuename':'name'}, \
                                   'episode':              {'listname':'episodes','keyname':'episode_key','valuename':'episode_number'}, \
                                   'episode_name':    {'listname':'episodes','keyname':'episode_key','valuename':'name'}, \
                                   'description':      {'listname':'episodes','keyname':'episode_key','valuename':'synopsis'}, \
                                   'nicam':                  {'listname':'episodes','keyname':'episode_key','valuename':'nicam'}}

    def get_url(self, abstract = None, days = 0):

        rtl_general = 'http://www.rtl.nl/system/s4m/tvguide/guide_for_one_day.xml?output=json'
        rtl_abstract = 'http://www.rtl.nl/system/s4m/tvguide/guide_for_one_abstract.xml?output=json'

        if abstract == None:
            channels = ''
            for chanid in self.channels.values():
                if len(channels) == 0:
                    channels = chanid

                else:
                    channels = '%s,%s' % (channels, chanid)

            return '%s&days_ahead=%s&days_back=%s&station=%s' % \
                ( rtl_general, (self.config.opt_dict['offset'] + self.config.opt_dict['days'] -1), - self.config.opt_dict['offset'], channels)

        else:
            return '%s&abstract_key=%s&days_ahead=%s' % ( rtl_abstract, abstract, days)

    def get_channels(self):
        self.all_channels = self.config.rtl_channellist

    def load_pages(self):

        if len(self.channels) == 0 :
            return

        self.config.log(['\n', 'Now fetching %s channels from rtl.nl for %s days.\n' %  (len(self.channels), self.config.opt_dict['days'])], 2)

        channel_url = self.get_url()

        # be nice to rtl.nl
        time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))

        # get the raw programming for the day
        strdata = self.config.fetch_func.get_page(channel_url, 'utf-8')

        if strdata == None or strdata.replace('\n','') == '{}':
            # Wait a while and try again
            time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
            strdata = self.config.fetch_func.get_page(channel_url, 'utf-8')
            if strdata == None or strdata.replace('\n','') == '{}':
                self.config.log("Error loading rtl json data\n")
                self.fail_count += 1
                for chanid in self.channels.keys():
                    self.config.channels[chanid].source_data[self.proc_id].set()

                return False

        # Just let the json library parse it.
        total = json.loads(strdata)
        self.base_count += 1
        # and find relevant programming info
        schedules = total['schedule']
        for r in schedules:
            self.schedule[r['station']].append(r)

        library = total['library'][0]

        for i in library['abstracts']:
            self.jsondict['abstracts'][i['abstract_key']] = i

        for i in library['seasons']:
           self.jsondict['seasons'][i['season_key']] = i

        for i in library['episodes']:
            self.jsondict['episodes'][i['episode_key']] = i

        self.page_loaded = True

        for chanid, channel in self.channels.iteritems():
            if len( self.schedule[channel]) == 0:
                self.config.channels[chanid].source_id[self.proc_id] = ''
                continue

            for item in self.schedule[channel]:
                tdict = self.functions.checkout_program_dict()
                tdict['prog_ID'][self.proc_id] = u'%s-%s' % (channel,  item['unixtime'])
                self.json_by_id[tdict['prog_ID'][self.proc_id]] = item
                tdict['source'] = 'rtl'
                tdict['channelid'] = chanid
                tdict['channel']  = self.config.channels[chanid].chan_name

                # The Title
                tdict['name'] = self.get_json_data(tdict['prog_ID'][self.proc_id],'abstract_name')
                if  tdict['name'] == None or tdict['name'] == '':
                    self.config.log('Can not determine program title\n')
                    continue

                # The timing
                tdict['unixtime']  =int( item['unixtime'])
                tdict['start-time']  = datetime.datetime.fromtimestamp(tdict['unixtime'], CET_CEST)
                tdict['offset'] = self.functions.get_offset(tdict['start-time'])
                tdict['rerun']  = (item['rerun'] == 'true')

                # The Season Number
                season = self.get_json_data(tdict['prog_ID'][self.proc_id],'season')
                tdict['season'] = int(season) if (season != None) else 0

                # The Episode Number, SubTitle and Descriptionseason
                episode = self.get_json_data(tdict['prog_ID'][self.proc_id],'episode')
                tdict['episode'] = int(episode) if (episode != None) else 0

                subtitle = self.get_json_data(tdict['prog_ID'][self.proc_id],'episode_name')
                tdict['titel aflevering'] = subtitle if ((subtitle != None) and (subtitle != tdict['name'])) else ''
                tdict = self.check_title_name(tdict)

                description = self.get_json_data(tdict['prog_ID'][self.proc_id],'description')
                tdict['description'] = description if (description != None) else ''

                nicam = self.get_json_data(tdict['prog_ID'][self.proc_id],'nicam')
                if '16' in nicam:
                    tdict['kijkwijzer'].append('4')

                elif '12' in nicam:
                    tdict['kijkwijzer'].append('3')

                elif '9' in nicam:
                    tdict['kijkwijzer'].append('9')

                elif '6' in nicam:
                    tdict['kijkwijzer'].append('2')

                elif 'AL' in nicam:
                    tdict['kijkwijzer'].append('1')

                for k in ('g', 'a', 's', 't', 'h', 'd'):
                    if k in nicam:
                        tdict['kijkwijzer'].append(k)

                with self.source_lock:
                    self.program_data[chanid].append(tdict)

            # Add starttime of the next program as the endtime
            with self.source_lock:
                self.program_data[chanid].sort(key=lambda program: (program['start-time']))
                self.add_endtimes(chanid, 7)

                for tdict in self.program_data[chanid]:
                    self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

            self.parse_programs(chanid, 0, 'None')
            self.channel_loaded[chanid] = True
            for day in range( self.config.opt_dict['offset'], (self.config.opt_dict['offset'] + self.config.opt_dict['days'])):
                self.day_loaded[chanid][day] = True

            self.config.channels[chanid].source_data[self.proc_id].set()
            try:
                self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

            except:
                pass

# end rtl_JSON

class teveblad_HTML(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the teveblad.be page. Based on FetchData
    """
    def init_channels(self):
        """ Site layout
            <head>
            <body>
                <div id="mainbox"></div>
                    <div>
                        <div class="epg_container">
                            <div class="epg_content" style="padding:10px 0 10px 0;">
                                <div id="epg" class="epg view_channels" baseurl="/tv-gids/{SELECTED_DATE}/zenders/npo-3" api="http://www.teveblad.be/api/teveblad/">
                                    <div id="epg_c">
                                        <div id="genrechanneloverview">
                                            <div id="smallleftcol">
                                                <div class="greyrounded">
                                                    <h2>
                                                        <a href="http://www.teveblad.be/tv-gids/2015-01-16/zendergroep/hoofd-zenders">Hoofdzenders</a>
                                                    </h2>
                                                    <a href="/tv-gids/2015-01-16/zenders/een">
                                                        <img src="http://s4.cdn.sanomamedia.be/a/epg/q100/w60/h/39043/een-nl.jpg" width="60" height="60" title="één" />
                                                    </a>
                                                        ...
                                                    <div class="clear20"></div>
                                                        ...
                                                </div>
                                            </div>
                                            <div id="middlecolchaine">
                                                <h1>
                                                    <img src="http://s3.cdn.sanomamedia.be/a/epg/q100/w50/h/1165805/npo-3.jpg" width="50" height="50" title="NPO 3" align="absmiddle" />&nbsp;&nbsp;NPO 3
                                                </h1>
                                                <div id="event_cbbc555459a8cfdd20178ab831d515d9" class="programme">
                                                    <div class="c">
                                                        <div class="l">
                                                            <span class="starttime">22u20</span>
                                                        </div>
                                                        <div class="r" class="toowide">
                                                            <p>
                                                                <span class="title">
                                                                    <a href="http://www.teveblad.be/tv-gids/programma/1250435/millennium-mannen-die-vrouwen-haten-1-2-seizoen-1-aflevering-1-6">Millennium</a>
                                                                </span><br />
                                                                <span class="title_episode" style="font-style:italic;">Mannen die vrouwen haten (1/2)</span>
                                                            </p>
                                                            <p class="desc_short">Misdaadserie</p>
                                                            <p class="basicinfo">
                                                                (<span class="year">2009</span>, <span class="country">DEU, DNK, NOR, SWE</span>) -
                                                                <span class="season">Season 1 (1/6)</span>
                                                            </p>
                                                            <div class="desc h">
                                                                <p>Onderzoeksjournalist Mikael Blomkvist krijgt een ongewone opdracht. De rijke industrieel Henrik Vanger vraagt hem zijn familiegeschiedenis neer te schrijven...</p>
                                                            </div>
                                                            <p class="picons">
                                                                <span class="genre series curvyIgnore">
                                                                    <a href="http://www.teveblad.be/tv-gids/2015-01-16/genres/serie">Serie</a>
                                                                </span>
                                                                <div class="clear"></div>
                                                            </p>
                                                        </div>
                                                        <div class="clear"></div>
                                                    </div>
                                                </div>
                                                    ...
        Detailpage (not implemented)
            <head>
            <body>
                <div id="mainbox"></div>
                <div>
                    <div>
                        <div id="content" class="narrowcolumn">
                            <div class="dialog">
                                <div class="content_rounded">
                                    <div id="epg_gridselector" class="program_detail_header"></div>
                                    <div class="epg programdetail">
                                        <div class="program_detail">
                                            <div><h2>Zaterdag 17 januari 2015 14u00</h2></div>
                                            <div class="programdetailsblock">
                                                <p class="basicinfo">
                                                    <h3>Care and Protection</h3>
                                                    <p>
                                                        <span class="season">Seizoen 1 (1/3)</span>
                                                    </p>
                                                    <p class="desc_short">Misdaadserie.</p>
                                                        (<span class="year">1992</span>,<span class="country">GBR</span>)
                                                </p>
                                                <p class="picons">
                                                    <span class="picon" title="Herhaling">HERH</span>
                                                    <div class="clear"></div>
                                                </p>
                                                <p class="picons">
                                                    <div class="clear"></div>
                                                </p>
                                                <div class="clear"></div>
                                                <p class="desc">Samen met detective Clive Barnard gaat Jack Frost op zoek naar een vermist meisje. Haar moeder is de prostitutie in gestapt om de rekeningen te kunnen betalen. Tijdens het onderzoek stoten Frost en Barnard op een misdaad die dertig jaar geleden werd begaan. Op het thuisfront heeft Frost het emotioneel erg zwaar met de hopeloze strijd van zijn vrouw tegen een ongeneeslijke ziekte...</p>
                                            </div>
                                            <div class="clear"></div>
                                            <div class="roles">
                                                <div class="group">
                                                    <p class="title_h2">Acteurs</p>
                                                    <ul>
                                                        <li>David Jason <span class="character">(D.I. Jack Frost)</span></li>
                                                        <li>Bruce Alexander <span class="character">(Superintendent Mullett)</span></li>
                                                        <li>Matt Bardock <span class="character">(DC Barnard)</span></li>
                                                        <li>Claire Hackett <span class="character">(Linda Uphill)</span></li>
                                                        <li>Ralph Nossek <span class="character">(Gerald Powell)</span></li>
                                                        <li>Lindy Whiteford <span class="character">(Shirley Fisher)</span></li>
                                                        <li>Helen Blatch <span class="character">(Annie)</span></li>
                                                    </ul>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div id="sidebar">
                    </div>
                    <div class="clear"></div>
                </div>
                <footer id="footer"></div>
            </body>
        """

        self.datecheckdata = re.compile('<input id="epg_dateselector".*?data-value="([0-9]+)-([0-9]+)-([0-9]+)".*?/>',re.DOTALL)
        self.channeldata = re.compile('<div id="smallleftcol">(.*?)<div id="middlecolchaine">',re.DOTALL)
        self.progdata = re.compile('<div id="middlecolchaine">(.*?)<div id="epg_grid_view">channels</div>',re.DOTALL)
        self.groupdata = re.compile('<div id="epg_channel_headers">(.*?)<div id="epg_scroller_right">.*?' + \
                                                    '<div id="epg_channels">(.*?)<div id="epg_scroller">',re.DOTALL)
        self.seasondata = re.compile('Season ([0-9]+) \(([0-9]+)/([0-9]+)\)',re.DOTALL)

        basepath = 'div[@id="mainbox"]/div/div[@class="epg_container"]/div[@class="epg_content"]/' + \
                                    'div[@id="epg"]/div[@id="epg_c"]/div[@id="genrechanneloverview"]/'
        self.channelpath = basepath + 'div[@id="smallleftcol"]/div[@id="class="greyrounded"]'

        self.init_channel_source_ids()

    def get_url(self, date = '', channel = '', get_group = False):

        teveblad_zoeken = 'http://www.teveblad.be/tv-gids/'
        if type(date) == datetime.datetime or type(date) == datetime.date:
            date = date.strftime('%Y-%m-%d') + u'/'
            if date == datetime.datetime.now(CET_CEST).strftime('%Y-%m-%d') + u'/':
                date = ''

        if get_group:
            return u'%s%szendergroep/%s' % (teveblad_zoeken,  date, channel)

        else:
            return u'%s%szenders/%s' % (teveblad_zoeken,  date, channel)

    def check_date(self, return_date, search_date):
        try:
            if return_date.group(1) == search_date.strftime('%Y'):
                if return_date.group(2) == search_date.strftime('%m'):
                    if return_date.group(3) == search_date.strftime('%d'):
                        return True

        except:
            self.config.log(['Invalid page returned by teveblad.be\n', 'return_date: %s search_date: %s\n' % (return_date, search_date)])
            return False

        self.config.log('Wrong date %s-%s-%s returned from teveblad.be, %s requested\n' % \
             (return_date.group(1),return_date.group(2) ,return_date.group(3) , search_date.strftime('%Y-%m-%d')))

        return False

    def read_channelfile(self):
        try:
            if not os.access(u'%s/teveblad_channels.html' % (self.config.opt_dict['xmltv_dir']), os.F_OK):
                if os.access(u'%s/teveblad_channels.html' % (self.config.opt_dict['home_dir']), os.F_OK):
                    self.config.log('copying %s/teveblad_channels.html to %s\n' % (self.config.opt_dict['home_dir'], self.config.opt_dict['xmltv_dir']))
                    shutil.copy(u'%s/teveblad_channels.html' % (self.config.opt_dict['home_dir']), self.config.opt_dict['xmltv_dir'])
                else:
                    self.config.log('teveblad channel info file: %s/teveblad_channels.html not found\n' % (self.config.opt_dict['home_dir']))
                    return None

            f = IO_func.open_file( u'%s/teveblad_channels.html' % self.config.opt_dict['xmltv_dir'])
            if f == None:
                return None

            strdata = u''
            for byteline in f.readlines():
                line = IO_func.get_line(f, byteline)
                strdata += self.functions.clean_html(line)
            f.close()

            return ET.fromstring(strdata.encode('utf-8'))

        except:
            self.config.log(['error parsing %s/teveblad_channels.html\n' % (self.config.opt_dict['xmltv_dir']), traceback.format_exc()])
            return None

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        try:
            strdata = self.config.fetch_func.get_page(self.get_url())
            if strdata == None:
                self.fail_count += 1
                htmldata = self.read_channelfile()
                if htmldata == None:
                    return None

            else:
                strdata = self.functions.clean_html('<div>' + self.channeldata.search(strdata).group(1)).encode('utf-8')
                htmldata = ET.fromstring(strdata)

        except:
            self.fail_count += 1
            htmldata = self.read_channelfile()
            if htmldata == None:
                return None

        chan_groups = {'Nederlandstalig': 2,
                                    'Hoofdzenders': 2,
                                    'Engelstalig': 3,
                                    'Franstalig': 5,
                                    'Digitale zenders': 9,
                                    'Documentaire': 9,
                                    'Sport': 9,
                                    'Kids & Jeugd': 9,
                                    'Anderstalige zenders': 10}
        self.all_channels ={}
        self.page_strings = {}
        changroup = 99
        for item in htmldata.find('div[@class="greyrounded"]'):
            if item.tag == 'h2':
                group =  self.functions.empersant(item.findtext('a[@href]'))
                if group in chan_groups:
                    changroup = chan_groups[group]

                else:
                    changroup = 99

                group_url = item.find('a').get('href')
                group_url = re.split('/', group_url)[-1]
                self.page_strings[group] = {}
                self.page_strings[group]['url'] = group_url
                self.page_strings[group]['chan_list'] = []
                self.page_strings[group]['fetch_list'] = []

            elif item.tag == 'a':
                chan = item.get('href')
                if chan != None:
                    chanid = re.split('/', chan)[-1]
                    i = item.find('img')
                    icon = '' if i == None else i.get('src', '')
                    if icon != '':
                        icon = re.split('/', icon)
                        icon = '%s/%s' % (icon[-2], icon[-1])

                    self.all_channels[chanid] = {}
                    t = item.find('img')
                    self.all_channels[chanid]['name'] = '' if t == None else t.get('title', '')
                    self.all_channels[chanid]['icon'] = icon
                    self.all_channels[chanid]['group'] = changroup
                    self.all_channels[chanid]['group_list'] = []
                    self.page_strings[group]['chan_list'].append(chanid)
                    if group == 'Digitale zenders':
                        self.all_channels[chanid]['HD'] = True

                    else:
                        self.all_channels[chanid]['HD'] = False

        for g, v in self.page_strings.items():
            for chanid in v['chan_list']:
                self.all_channels[chanid]['group_list'].append(g)


    def load_pages(self):
        if self.config.opt_dict['offset'] > 8:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        # We first try to get the solopages
        self.load_solopages()
        # And for the failed pages we try the grouppages
        self.load_grouppages()

    def load_grouppages(self):
        # First determin which pages need to be loaded
        try:
            self.get_channels()
            # Init loaded markings for the grouppages
            for n, v in self.page_strings.items():
                v['fetch_list'] = []
                self.day_loaded[n] = {}
                for day in range( self.config.opt_dict['offset'], (self.config.opt_dict['offset'] + self.config.opt_dict['days'])):
                    self.day_loaded[n][day] = False

            for chanid, channel in self.channels.items():
                if not channel in self.all_channels:
                    # This channel is removed, for it reurns empty
                    self.channel_loaded[chanid] = True
                    self.config.channels[chanid].source_data[self.proc_id].set()
                    continue

                # Check wich grouppage to load
                if not self.channel_loaded[chanid] and len(self.all_channels[channel]['group_list']) > 0:
                    self.page_strings[self.all_channels[channel]['group_list'][0]]['fetch_list'].append(channel)

            for retry in (0, 1):
                # There are 9 group pages. Check if any channel from a page is wanted
                for group_page, group_values in self.page_strings.items():
                    if len(group_values['fetch_list']) == 0:
                        continue

                    failure_count = 0
                    if self.quit:
                        return

                    # teeveeblad.be shows programs per day, so we loop over the number of days
                    # we are required to grab
                    days = min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 8)
                    for offset in range(self.config.opt_dict['offset'], days):
                        if self.day_loaded[group_page][offset] != False:
                            continue

                        day_list = []
                        for channel in group_values['fetch_list']:
                            chanid = ''
                            for k, v in self.channels.items():
                                if channel == v:
                                    chanid = k
                                    if not self.day_loaded[chanid][offset]:
                                        day_list.append(chanid)

                                    break

                            if len(day_list) > 0:
                                break

                        else:
                            if len(day_list) == 0:
                                # All channels processed for this day
                                continue

                        self.config.log(['\n', 'Now fetching GroupPage: %s from teveblad.be for day %s of %s.\n' % (group_page, offset, days-config.opt_dict['offset'])], 2)

                        date_offset = offset
                        scan_date = datetime.date.fromordinal(self.current_date + offset)
                        channel_url =self.get_url(scan_date, group_values['url'], True)

                        # get the raw programming for the day
                        strdata = self.config.fetch_func.get_page(channel_url, encoding = 'utf-8')

                        if strdata == None:
                            self.config.log("Skip %s page on teveblad.be, day=%d. No data!\n" % (group_page, offset))
                            failure_count += 1
                            self.fail_count += 1
                            continue

                        if not self.check_date(self.datecheckdata.search(strdata), scan_date):
                            self.config.log("Skip group=%s on teveblad.be, day=%d. Wrong date!\n" % (group_page, offset))
                            failure_count += 1
                            self.fail_count += 1
                            continue

                        # and extract the ElementTree
                        try:
                            strdata = self.functions.clean_html(strdata)
                            strdata = re.sub('<div class="r" class="toowide">', '<div class="r">', strdata)
                            strdata =self.groupdata.search(strdata)
                            strdata = u'<root><div>' + strdata.group(1) + u'\n<div>\n' + strdata.group(2) + u'</root>'
                            htmldata = ET.fromstring(strdata.encode('utf-8'))

                        except:
                            self.config.log(['Error extracting ElementTree for zendergroup:%s day:%s\n' % (group_page, offset), traceback.format_exc()])
                            if self.config.write_info_files:
                                self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                                self.config.infofiles.write_raw_string(unicode(strdata + u'\n'))

                            self.day_loaded[group_page][offset] = None
                            self.fail_count += 1
                            continue

                        self.base_count += 1
                        channel_cnt = 0
                        chan_list = {}
                        # Retrieve the available channels and add the wanted channels to the channel list
                        for c in  htmldata.findall('div/div[@id="epg_channel_headers_content"]/div[@class="channel"]'):
                            url = c.find('div/a').get('href')
                            if url != None:
                                channel_cnt += 1
                                c = re.split('/', url)[-1]
                                if c in group_values['fetch_list']:
                                    chan_list[unicode(channel_cnt)] = c

                        for c in  htmldata.findall('div/div[@id="epg_channels_content"]/div[@class="channel"]'):
                            if not c.get('number') in chan_list.keys():
                                continue

                            last_program = datetime.datetime.combine(scan_date, datetime.time(1, 0, 0 ,0 ,CET_CEST))
                            channel = chan_list[c.get('number')]
                            for k, v in self.channels.items():
                                if channel == v:
                                    chanid = k

                            for p in c.findall('div'):
                                if not( p.get('class') == 'programme even' or p.get('class') == 'programme odd'):
                                    continue

                                p_duur = int(p.get('duration'))
                                tdict = self.functions.checkout_program_dict()
                                p = p.find('div[@class="c"]')
                                tdict['source'] = 'teveblad'
                                tdict['channelid'] = chanid
                                tdict['channel'] = self.config.channels[chanid].chan_name

                                # The Title
                                title = p.find('p/span[@class="title"]')
                                if title == None:
                                    self.config.log('Can not determine program title"\n')
                                    continue

                                href = title.find('a').get('href')
                                if href != '' and href != None:
                                    tdict['detail_url'][self.proc_id] = title.find('a').get('href')
                                    tdict['prog_ID'][self.proc_id] = u'be-%s' % tdict['detail_url'][self.proc_id].split('/')[5]
                                tdict['name'] = self.functions.empersant(title.findtext('a'))
                                if tdict['name'] == None or  tdict['name'] == '':
                                    self.config.log('Can not determine program title for "%s"\n' % tdict['be-url'])
                                    continue

                                # Starttime
                                start = p.findtext('p/span[@class="starttime"]')
                                if start == None or start == '':
                                    self.config.log('Can not determine starttime for "%s"\n' % tdict['name'])
                                    continue

                                prog_time = datetime.time(int(start.split('u')[0]), int(start.split('u')[1]), 0 ,0 ,CET_CEST)

                                # Make sure the midnight date change is properly crossed
                                if datetime.datetime.combine(scan_date, prog_time) < last_program:
                                    date_offset = offset +1
                                    scan_date = datetime.date.fromordinal(self.current_date + date_offset)
                                tdict['offset'] = date_offset
                                tdict['start-time'] = datetime.datetime.combine(scan_date, prog_time)
                                last_program = tdict['start-time']
                                tdict['stop-time'] = tdict['start-time'] + datetime.timedelta(0, 0, 0, 0, p_duur)

                                # Subtitle
                                subtitle = self.functions.empersant(p.findtext('p/span[@class="title_episode"]'))
                                tdict['titel aflevering'] = subtitle if (subtitle != None) else ''

                                # Description. There is a possible long and short version. We try to take the long one
                                descshort = self.functions.empersant(p.findtext('p/span[@class="desc_short"]'))
                                descshort = '' if (descshort == None) else descshort

                                desc = self.functions.empersant(p.findtext('div[@class="desc h"]/p'))
                                tdict['description'] = desc if (desc != None) else descshort

                                # The basicinfo section
                                for d in p.iterfind('div[@class="basicinfo"]/span'):

                                    if d.get('class').lower() == 'year':
                                        tdict['jaar van premiere'] = d.text

                                    elif d.get('class').lower() == 'episode':
                                        tdict['episode'] = (re.sub('Episode', '', d.text)).strip()
                                        tdict['episode'] = int((re.sub('Aflevering', '', d.text)).strip())

                                    elif d.get('class').lower() == 'season':
                                        try:
                                            season = self.seasondata.search(d.text)
                                            if season != None:
                                                tdict['season'] = int(season.group(1))
                                                tdict['episode'] = int(season.group(2))
                                                #stotal = season.group(3)

                                        except:
                                            if self.config.write_info_files:
                                                self.config.infofiles.addto_detail_list('error processing seasonstring: %s\n\n' % season)

                                    elif d.get('class').lower() == 'desc_short' and tdict['description'] == '':
                                        tdict['description'] = self.functions.empersant(d.text)

                                    elif d.get('class').lower() == 'originaltitle':
                                        tdict['originaltitle'] = self.functions.empersant(d.text)

                                    # We don't use it (yet)
                                    elif d.get('class').lower() == 'country':
                                        continue

                                    elif self.config.write_info_files:
                                        self.config.infofiles.addto_detail_list(unicode('new teveblad basicinfo => ' + d.get('class') + '=' + d.text))

                                # The picons section
                                for d in p.iterfind('p[@class="picons"]/span'):

                                    if d.get('class').lower() == 'picon' or d.get('class').lower() == 'curvyignore picon' :

                                        # We don't use these (yet)
                                        if d.get('title').lower() in ('gedubd', 'live', 'ingekleurd'):
                                            continue

                                        if d.get('title').lower() == 'herhaling':
                                            tdict['rerun'] = True

                                        elif d.get('title').lower() == 'nieuw':
                                            tdict['new'] = True

                                        elif d.get('title').lower() == 'laatste aflevering':
                                            tdict['last-chance'] = True

                                        elif d.get('title').lower() == 'premiere':
                                            tdict['premiere'] = True

                                        elif d.get('title').lower() == 'hd':
                                            tdict['video']['HD'] = True

                                        elif d.get('title').lower() == 'dolby':
                                            tdict['audio']  = 'dolby'

                                        elif d.get('title').lower() == '16:9':
                                            tdict['breedbeeld']  = True

                                        elif d.get('title').lower() == 'ondertiteld':
                                            tdict['teletekst']  = True

                                        elif self.config.write_info_files:
                                            self.config.infofiles.addto_detail_list(unicode('new teveblad picondata => ' + d.get('title') + '=' + d.text))

                                    elif 'genre' in d.get('class').lower():
                                        genre = self.functions.empersant(d.findtext('a'))
                                        if genre == '' or genre == None:
                                            continue

                                        if genre.lower() in self.config.source_cattrans[self.proc_id].keys():
                                            tdict['genre'] = self.config.source_cattrans[self.proc_id][genre.lower()][0].capitalize()
                                            tdict['subgenre'] = self.config.source_cattrans[self.proc_id][genre.lower()][1].capitalize()

                                        else:
                                            self.config.new_cattrans[self.proc_id][genre] = (u'Overige', u'')

                                for d in p.iterfind('span[@class]'):
                                    if 'genre' in d.get('class').lower():
                                        genre = self.functions.empersant(p.findtext('a'))
                                        if genre == '' or genre == None:
                                            continue

                                        if genre.lower() in self.config.source_cattrans[self.proc_id].keys():
                                            tdict['genre'] = self.config.source_cattrans[self.proc_id][genre.lower()][0].capitalize()
                                            tdict['subgenre'] = self.config.source_cattrans[self.proc_id][genre.lower()][1].capitalize()

                                        else:
                                            self.config.new_cattrans[self.proc_id][genre] = (u'Overige', u'')

                                # and append the program to the list of programs
                                tdict = self.check_title_name(tdict)
                                with self.source_lock:
                                    self.program_data[chanid].append(tdict)

                            self.day_loaded[chanid][offset] = True

                        self.day_loaded[group_page][offset] = True
                        # be nice to teveblad.be
                        time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))

                    # If all went well or it's the last try we set them loaded
                    if failure_count == 0 or retry == 1:
                        for chanid, channel in self.channels.items():
                            if channel in group_values['fetch_list']:
                                with self.source_lock:
                                    for tdict in self.program_data[chanid]:
                                        self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

                                self.channel_loaded[chanid] = True
                                self.parse_programs(chanid, 0, 'None')
                                self.config.channels[chanid].source_data[self.proc_id].set()

                                try:
                                    self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                                except:
                                    pass

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread:\n' %  (self.source), traceback.format_exc()], 0)

            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()
            return None

    def load_solopages(self):

        for retry in (0, 1):
            channel_cnt = 0
            for chanid in self.channels.keys():
                channel_cnt += 1
                failure_count = 0
                if self.quit:
                    return

                channel = self.channels[chanid]

                # teeveeblad.be shows programs per day, so we loop over the number of days
                # we are required to grab
                days = min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 8)
                for offset in range(self.config.opt_dict['offset'], days):
                    if self.day_loaded[chanid][offset] != False:
                        continue

                    self.config.log(['\n', 'Now fetching %s(xmltvid=%s%s) from teveblad.be\n' % \
                        (self.config.channels[chanid].chan_name, self.config.channels[chanid].xmltvid, (self.config.channels[chanid].opt_dict['compat'] and '.tvgids.nl' or '')), \
                        '    (channel %s of %s) for day %s of %s days.\n' % \
                        ( channel_cnt, len(self.channels), offset, days-config.opt_dict['offset'])], 2)

                    date_offset = offset
                    scan_date = datetime.date.fromordinal(self.current_date + offset)
                    last_program = datetime.datetime.combine(scan_date, datetime.time(1, 0, 0 ,0 ,CET_CEST))
                    channel_url =self.get_url(scan_date, channel)

                    # get the raw programming for the day
                    strdata = self.config.fetch_func.get_page(channel_url)

                    if strdata == None:
                        self.config.log("Skip channel=%s on teveblad.be, day=%d. No data!\n" % (self.config.channels[chanid].chan_name, offset))
                        failure_count += 1
                        self.fail_count += 1
                        continue

                    if not self.check_date(self.datecheckdata.search(strdata), scan_date):
                        self.config.log("Skip channel=%s on teveblad.be, day=%d. Wrong date!\n" % (self.config.channels[chanid].chan_name, offset))
                        failure_count += 1
                        self.fail_count += 1
                        continue

                    # and extract the ElementTree
                    try:
                        strdata = self.functions.clean_html(strdata)
                        strdata = re.sub('<div class="r" class="toowide">', '<div class="r">', strdata)
                        strdata = u'<div><div>' + self.progdata.search(strdata).group(1)
                        htmldata = ET.fromstring(strdata.encode('utf-8'))
                        if htmldata.findtext('div/p') == "We don't have any events for this broadcaster":
                            self.config.channels[chanid].source_data[self.proc_id].set()
                            for i in range(self.config.opt_dict['offset'], days):
                                self.day_loaded[chanid][i] = None
                            break

                    except:
                        self.config.log('Error extracting ElementTree for channel:%s day:%s\n' % (self.config.channels[chanid].chan_name, offset))
                        if self.config.write_info_files:
                            self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                            self.config.infofiles.write_raw_string(strdata + u'\n')

                        self.day_loaded[chanid][offset] = None
                        self.fail_count += 1
                        continue

                    self.base_count += 1
                    for p in htmldata.findall('div/div[@class="programme"]'):
                        tdict = self.functions.checkout_program_dict()
                        p = p.find('div[@class="c"]')
                        tdict['source'] = 'teveblad'
                        tdict['channelid'] = chanid
                        tdict['channel'] = self.config.channels[chanid].chan_name

                        # The Title
                        title = p.find('div[@class="r"]/p/span[@class="title"]')
                        if title == None:
                            self.config.log('Can not determine program title"\n')
                            continue

                        href = title.find('a').get('href')
                        if href != '' and href != None:
                            tdict['detail_url'][self.proc_id] = title.find('a').get('href')
                            tdict['prog_ID'][self.proc_id] = u'be-%s' % tdict['detail_url'][self.proc_id].split('/')[5]
                        tdict['name'] = self.functions.empersant(title.findtext('a'))
                        if tdict['name'] == None or  tdict['name'] == '':
                            self.config.log('Can not determine program title for "%s"\n' % tdict['be-url'])
                            continue

                        # Starttime
                        start = p.findtext('div[@class="l"]/span[@class="starttime"]')
                        if start == None or start == '':
                            self.config.log('Can not determine starttime for "%s"\n' % tdict['name'])
                            continue

                        prog_time = datetime.time(int(start.split('u')[0]), int(start.split('u')[1]), 0 ,0 ,CET_CEST)

                        # Make sure the midnight date change is properly crossed
                        if datetime.datetime.combine(scan_date, prog_time) < last_program:
                            date_offset = offset +1
                            scan_date = datetime.date.fromordinal(self.current_date + date_offset)
                        tdict['offset'] = date_offset
                        tdict['start-time'] = datetime.datetime.combine(scan_date, prog_time)
                        last_program = tdict['start-time']

                        # Subtitle
                        subtitle = self.functions.empersant(p.findtext('div[@class="r"]/p/span[@class="title_episode"]'))
                        tdict['titel aflevering'] = subtitle if (subtitle != None) else ''

                        # Description. There is a possible long and short version. We try to take the long one
                        descshort = self.functions.empersant(p.findtext('div[@class="r"]/p[@class="desc_short"]'))
                        descshort = '' if (descshort == None) else descshort

                        desc = self.functions.empersant(p.findtext('div[@class="r"]/div[@class="desc h"]/p'))
                        tdict['description'] = desc if (desc != None) else descshort

                        # The basicinfo section
                        for d in p.iterfind('div[@class="r"]/p[@class="basicinfo"]/span'):

                            if d.get('class').lower() == 'year':
                                tdict['jaar van premiere'] = d.text

                            elif d.get('class').lower() == 'episode':
                                tdict['episode'] = int((re.sub('Episode', '', d.text)).strip())

                            elif d.get('class').lower() == 'season':
                                season = self.seasondata.search(d.text)
                                tdict['season'] = int(season.group(1))
                                tdict['episode'] = int(season.group(2))
                                #stotal = season.group(3)

                            elif d.get('class').lower() == 'originaltitle':
                                tdict['originaltitle'] = self.functions.empersant(d.text)

                            elif d.get('class').lower() == 'country':
                                tdict['country'] = self.functions.empersant(d.text)[0:2]
                                if self.config.write_info_files:
                                    self.config.infofiles.addto_detail_list(unicode('new teveblad county => ' + d.text))


                            elif self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(unicode('new teveblad basicinfo => ' + d.get('class') + '=' + d.text))

                        # The picons section
                        for d in p.iterfind('div[@class="r"]/p[@class="picons"]/span'):

                            if d.get('class').lower() == 'picon' or d.get('class').lower() == 'curvyignore picon' :

                                # We don't use these (yet)
                                if d.get('title').lower() in ('gedubd', 'live', 'ingekleurd'):
                                    continue

                                elif d.get('title').lower() == 'herhaling':
                                    tdict['rerun'] = True

                                elif d.get('title').lower() == 'nieuw':
                                    tdict['new'] = True

                                elif d.get('title').lower() == 'laatste aflevering':
                                    tdict['last-chance'] = True

                                elif d.get('title').lower() == 'premiere':
                                    tdict['premiere'] = True

                                elif d.get('title').lower() == 'hd':
                                    tdict['video']['HD'] = True

                                elif d.get('title').lower() == 'dolby':
                                    tdict['audio']  = 'dolby'

                                elif d.get('title').lower() == 'ondertiteld':
                                    tdict['teletekst']  = True

                                elif self.config.write_info_files:
                                    self.config.infofiles.addto_detail_list(unicode('new teveblad picondata => ' + d.get('title') + '=' + d.text))

                            elif 'genre' in d.get('class').lower():
                                genre = self.functions.empersant(d.findtext('a'))
                                if genre == '' or genre == None:
                                    continue

                                if genre.lower() in self.config.source_cattrans[self.proc_id].keys():
                                    tdict['genre'] = self.config.source_cattrans[self.proc_id][genre.lower()][0].capitalize()
                                    tdict['subgenre'] = self.config.source_cattrans[self.proc_id][genre.lower()][1].capitalize()

                                else:
                                    self.config.new_cattrans[self.proc_id][genre] = (u'Overige', u'')

                        # and append the program to the list of programs
                        tdict = self.check_title_name(tdict)
                        with self.source_lock:
                            self.program_data[chanid].append(tdict)

                    self.day_loaded[chanid][offset] = True
                    # be nice to teveblad.be
                    time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))

                # Add starttime of the next program as the endtime
                with self.source_lock:
                    self.program_data[chanid].sort(key=lambda program: (program['start-time']))
                    self.add_endtimes(chanid, 7)

                    for tdict in self.program_data[chanid]:
                        self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

                # If all went well we set them loaded. Else we give the grouppages a try
                if failure_count == 0:
                    self.channel_loaded[chanid] = True
                    self.parse_programs(chanid, 0, 'None')
                    self.config.channels[chanid].source_data[self.proc_id].set()

                try:
                    self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                except:
                    pass

# end teveblad_HTML

class npo_HTML(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the npo.nl page. Based on FetchData Class
    """
    def init_channels(self):
        """ General Site layout
            <div class='guides-overlay overlay'></div>
            <div class='row-fluid'>
                <div class='span12'>
                    <div         class='vertical-guide'
                                    data-counter='?npo-nl.gids.verticaal.20150526'
                                    data-end='Wed, 27 May 2015 05:59:59 +0200'
                                    data-keyboard-input='true'
                                    data-scorecard='{"prefix":"npo","name":"gids.verticaal.26-05-2015"}'
                                    data-slide-increment='540'
                                    data-start='Tue, 26 May 2015 06:00:00 +0200'
                                    id='primary-guide'>
                        <div class='guide-scroller'>
                            <div class='vertical-guide-wrapper'>
                                <ul class='scroll-header'>
                                    <li>
                                        <a href="/live/npo-1" title="Bekijk live!">
                                            <div alt='Logo van NPO 1'
                                                    class='channel-logo'
                                                    style="background-image: url('//assets.www.npo.nl/uploads/tv_channel/263/logo/regular_logo-npo1.png')">
                                            </div>
                                                NPO 1
                                        </a>
                                    </li>
                                        ...
                                    <li class='ttv'>
                                        <div alt='Logo van NPO Nieuws'
                                                class='channel-logo'
                                                style="background-image: url('//assets.www.npo.nl/uploads/tv_channel/279/guide_label/regular_nponieuws-klein.png')">
                                        </div>
                                            NPO Nieuws
                                    </li>
                                        ...
                                    <li class='rtv'>
                                        <div alt='Logo van Regio TV Utrecht'
                                                class='channel-logo'
                                                style="background-image: url('//assets.www.npo.nl/uploads/tv_channel/273/logo/regular_rtvutrecht.png')">
                                        </div>
                                            Regio TV Utrecht
                                    </li>
                                </ul>
                                <table>
                                    <tr class='odd' data-hour='6'>          ('6' - '5')
                                        <td class='padder left'></td>
                                        <td class='red'>                             ('red', 'blue', 'green', 'ttv'..., 'rtv'...)
                                            <a           href="/nederland-in-beweging/25-05-2015/POW_00979881"
                                                            class="time-block inactive"
                                                            data-end-hour="06"
                                                            data-end-minutes="07"
                                                            data-genre="17"
                                                            data-start-hour="05"
                                                            data-start-minutes="53">
                                                <div class='time'>05:53</div>
                                                <div class='description'>
                                                    <i class='np'></i>
                                                    <div class='program-title'>Nederland in Beweging</div>
                                                </div>
                                            </a>
                                                ...
                                        </td>
                                                ...

                                        <td class='padder right'></td>
                                    <tr class='odd active' data-hour='1'>
                                        ...
                                    </tr>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        """

        self.init_channel_source_ids()
        self.chanids = {}
        for chanid, sourceid in self.channels.items():
            self.chanids[sourceid] = chanid

    def get_url(self, offset = 0, href = None, vertical = False):

        npo_zoeken = 'http://www.npo.nl'
        if href == None and vertical:
            scan_date = datetime.date.fromordinal(self.current_date + offset)
            return u'%s/gids/verticaal/%s/content' % (npo_zoeken,  scan_date.strftime('%d-%m-%Y'))

        if href == None and not vertical:
            scan_date = datetime.date.fromordinal(self.current_date + offset)
            return u'%s/gids/horizontaal/%s/content' % (npo_zoeken,  scan_date.strftime('%d-%m-%Y'))

        elif href == '':
            return ''

        else:
            return u'%s%s' % (npo_zoeken,  href)

    def get_channels(self):
        try:
            strdata = self.config.fetch_func.get_page(self.get_url())
            strdata = self.functions.clean_html(strdata)
            if strdata == None:
                self.fail_count += 1
                self.config.log(["Unable to get channel info from %s\n" % self.source])
                return 69  # EX_UNAVAILABLE

            htmldata = ET.fromstring( (u'<root>\n' + strdata + u'\n</root>\n').encode('utf-8'))
            self.get_channel_lineup(htmldata)

        except:
            self.fail_count += 1
            self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
            return 69  # EX_UNAVAILABLE

    def get_channel_lineup(self, htmldata):
        chan_list = []
        channel_cnt = 0
        for c_grp in htmldata.findall('div'):
            if c_grp.find('div[@class="span12"]') == None:
                # The list of extra groups
                continue

            g_class = c_grp.get('class')
            g_id = c_grp.get('id')
            if  g_class == 'row-fluid':
                # The NPO base channels
                cgrp = 1

            elif g_id == 'themed-guide':
                # The NPO theme channels
                cgrp = 1

            elif g_id == 'regional-guide':
                # The Regional channels
                cgrp = 6

            elif g_id == 'radio-guide':
                # The Radio channels
                cgrp = 11

            else:
                # Unknown Group
                cgrp = 99

            for c in c_grp.findall('div[@class="span12"]/div/div[@class="guide-channel-icons"]/div[@class="channel-icon"]'):
                try:
                    if c.find('a') != None:
                        tag = c.find('a')
                        c = tag
                        if tag.get("alt") != None:
                            cname = self.functions.empersant(tag.get("alt")[9:])

                        else:
                            cname = self.functions.empersant(tag.get("href").split('/')[-1])

                    else:
                        cname = self.functions.empersant(c.find('div').get("title"))

                    try:
                        cicon = c.find('div[@class="larger-image channel-icon-wrapper"]').get('style')

                    except:
                        cicon = c.find('div[@class="larger-image channel-icon-wrapper no-shadow"]').get('style')

                    cicon = cicon.split('/')
                    scid = cicon[-3]
                    cicon = ('%s/%s/%s/%s' % (cicon[-4], cicon[-3], cicon[-2], cicon[-1]))[0:-2]
                    channel_cnt += 1
                    if scid == '301':
                        #301: NPO Zapp = 265: NPO 3
                        scid = '265'
                        cname = 'NPO 3'
                        cicon = 'tv-channel/265/logo/regular_logo-npo3.png'

                    self.all_channels[scid] = {}
                    self.all_channels[scid]['name'] = cname
                    self.all_channels[scid]['group'] = cgrp
                    self.all_channels[scid]['icongrp'] = 7
                    self.all_channels[scid]['icon'] = cicon
                    chan_list.append(scid)

                except:
                    self.config.log(['An error ocured while reading NPO channel info.', traceback.format_exc()])
                    continue

        return chan_list

    def load_pages(self):

        first_fetch = True
        def get_programs(xml, chanid, omroep = True):
            try:
                tdict = None
                day_offset = 0
                for p in xml.findall('a'):
                    ptext = p.find('i[@class="np"]')
                    if ptext == None:
                        # No title Found
                        continue

                    ptime = p.get('data-time')
                    if ptime == None:
                        # No start-stop time Found
                        continue

                    tdict = self.functions.checkout_program_dict()
                    tdict['source'] = u'npo'
                    tdict['channelid'] = chanid
                    tdict['channel'] = self.config.channels[chanid].chan_name
                    tdict['detail_url'][self.proc_id] = self.get_url(href = p.get('href',''))
                    if tdict['detail_url'][self.proc_id] != '':
                        pid = tdict['detail_url'][self.proc_id].split('/')[-1]
                        tdict['prog_ID'][self.proc_id] = u'npo-%s' % pid.split('_')[-1]

                    # The Title
                    tdict['name'] = self.functions.empersant(ptext.tail.strip())

                    ptime = ptime.split('-')
                    pstart = ptime[0].split(':')
                    prog_time = datetime.time(int(pstart[0]), int(pstart[1]), 0 ,0 ,CET_CEST)
                    if day_offset == 0 and int(pstart[0]) < 6:
                        day_offset = 1

                    tdict['offset'] = offset + day_offset

                    if day_offset == 1:
                        tdict['start-time'] = datetime.datetime.combine(nextdate, prog_time)

                    else:
                        tdict['start-time'] = datetime.datetime.combine(startdate, prog_time)

                    pstop = ptime[1].split(':')
                    prog_time = datetime.time(int(pstop[0]), int(pstop[1]), 0 ,0 ,CET_CEST)
                    if day_offset == 1 or int(pstop[0]) < 6:
                        tdict['stop-time'] = datetime.datetime.combine(nextdate, prog_time)

                    else:
                        tdict['stop-time'] = datetime.datetime.combine(startdate, prog_time)

                    if omroep:
                        tdict['omroep'] = p.findtext('span', '')

                    pgenre = p.get('data-genre','')
                    if pgenre != None and pgenre !=  '':
                        pgenre = pgenre.lower()
                        pg = pgenre.split(',', 1)
                        if len(pg) == 1:
                            pg = (pg[0].strip(), )

                        elif len(pg) == 2:
                            pg = (pg[0].strip(), pg[1].strip())

                        if pg in self.config.source_cattrans[self.proc_id].keys():
                            tdict['genre'] = self.config.source_cattrans[self.proc_id][pg][0].capitalize()
                            tdict['subgenre'] = self.config.source_cattrans[self.proc_id][pg][1].capitalize()

                        else:
                            if len(pg) > 1 and (pg[0].lower(), ) in self.config.source_cattrans[self.proc_id].keys():
                                tdict['genre'] = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )][0].capitalize()
                                tdict['subgenre'] = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )][1].capitalize()
                                self.config.new_cattrans[self.proc_id][(pg[0], pg[1])] = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )]

                            else:
                                tdict['genre'] = u'overige'
                                if len(pg) == 2:
                                    tdict['subgenre'] = pg[1].capitalize()
                                    self.config.new_cattrans[self.proc_id][pg] = (u'Overige', pg[1])

                                else:
                                    self.config.new_cattrans[self.proc_id][pg] = (u'Overige', u'')

                            if self.config.write_info_files and pgenre != '':
                                self.config.infofiles.addto_detail_list(unicode('unknown npo.nl genre => ' + pgenre + ': ' + tdict['name']))

                    else:
                        tdict['genre'] = u'overige'

                    # and append the program to the list of programs
                    tdict = self.check_title_name(tdict)
                    if last_added[chanid] != None and last_added[chanid]['name'] == tdict['name']:
                        with self.source_lock:
                            self.program_data[chanid][-1]['stop-time'] = tdict['stop-time']

                    else:
                        with self.source_lock:
                            self.program_data[chanid].append(tdict)

                    last_added[chanid] = None

                last_added[chanid] = tdict

            except:
                self.config.log(traceback.format_exc())

        if self.config.opt_dict['offset'] > 7:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        last_added = {}
        for retry in (0, 1):
            for offset in range(self.config.opt_dict['offset'], min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 7)):
                if self.quit:
                    return

                # Check if it is already loaded
                if self.day_loaded[0][offset]:
                    continue

                self.config.log(['\n', 'Now fetching %s channels from npo.nl\n' % (len(self.channels)), \
                    '    (day %s of %s).\n' % (offset, self.config.opt_dict['days'])], 2)

                channel_url = self.get_url(offset)

                if not first_fetch:
                    # be nice to npo.nl
                    time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
                    first_fetch = false

                # get the raw programming for the day
                strdata = self.config.fetch_func.get_page(channel_url)
                if strdata == None or 'We hebben deze pagina niet gevonden...' in strdata:
                    self.config.log("No data on npo.nl for day=%d\n" % (offset))
                    self.fail_count += 1
                    continue

                try:
                    strdata = self.functions.clean_html(strdata)
                    htmldata = ET.fromstring( (u'<root>\n' + strdata + u'\n</root>\n').encode('utf-8'))

                except:
                    self.config.log('Error extracting ElementTree for day:%s on npo.nl\n' % (offset))
                    self.fail_count += 1
                    if self.config.write_info_files:
                        self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                        self.config.infofiles.write_raw_string(u'<root>\n' + strdata + u'\n</root>\n')

                    continue

                # First we get the line-up and some date checks
                self.base_count += 1
                try:
                    startdate = htmldata.find('div[@class="row-fluid"]/div[@class="span12"]/div').get('data-start')
                    nextdate = htmldata.find('div[@class="row-fluid"]/div[@class="span12"]/div').get('data-end')
                    if startdate == None or nextdate == None:
                        self.config.log('Error validating page for day:%s on npo.nl\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno, offset))
                        continue

                    d = (startdate.split(',')[-1].strip()).split(' ')
                    startdate = datetime.datetime.strptime('%s %s %s' % (d[0], d[1], d[2]),'%d %b %Y').date()

                    d = (nextdate.split(',')[-1].strip()).split(' ')
                    nextdate = datetime.datetime.strptime('%s %s %s' % (d[0], d[1], d[2]),'%d %b %Y').date()

                    lineup = self.get_channel_lineup(htmldata)

                except:
                    self.config.log(traceback.format_exc())
                    continue

                try:
                    channel_cnt = 0
                    for c in htmldata.findall('div/div[@class="span12"]/div/div[@class="guide-scroller"]/div/div[@class="channels"]/div'):

                        scid = lineup[channel_cnt]
                        channel_cnt += 1
                        if not scid in self.chanids.keys():
                            continue

                        chanid = self.chanids[scid]
                        if not chanid in last_added:
                            last_added[chanid] = None

                        get_programs(c, chanid, self.all_channels[scid]['group'] in (1, 7, 11))
                        self.day_loaded[chanid][offset] = True

                except:
                    self.config.log(traceback.format_exc())

                self.day_loaded[0][offset] = True

        for chanid in self.channels.keys():
            self.channel_loaded[chanid] = True
            if len(self.program_data[chanid]) == 0:
                self.config.channels[chanid].source_data[self.proc_id].set()
                continue

            with self.source_lock:
                for tdict in self.program_data[chanid]:
                    self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

            self.parse_programs(chanid, 0, 'none')
            self.config.channels[chanid].source_data[self.proc_id].set()

            try:
                self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

            except:
                pass

    def load_pages_vertical(self):

        first_fetch = True
        if self.config.opt_dict['offset'] > 3:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        for offset in range(self.config.opt_dict['offset'], min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 3)):
            if self.quit:
                return

            self.config.log(['\n', 'Now fetching %s channels from npo.nl\n' % len(self.channels), \
            '    (day %s of %s).\n' % (offset, self.config.opt_dict['days'])], 2)

            channel_url = self.get_url(offset, None, True)

            if not first_fetch:
                # be nice to npo.nl
                time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
                first_fetch = false

            # get the raw programming for the day
            strdata = self.config.fetch_func.get_page(channel_url)
            if strdata == None or 'We hebben deze pagina niet gevonden...' in strdata:
                self.config.log("No data on npo.nl for day=%d\n" % (offset))
                self.fail_count += 1
                continue

            try:
                strdata = self.functions.clean_html(strdata)
                htmldata = ET.fromstring( (u'<root>\n' + strdata + u'\n</root>\n').encode('utf-8'))

            except:
                self.config.log('Error extracting ElementTree for day:%s on npo.nl\n' % (offset))
                self.fail_count += 1
                if self.config.write_info_files:
                    self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                    self.config.infofiles.write_raw_string(u'<root>\n' + strdata + u'\n</root>\n')

                continue

            # First we check for a changed line-up
            self.base_count += 1
            try:
                startdate = htmldata.find('div/div/div').get('data-start')
                nextdate = htmldata.find('div/div/div').get('data-end')
                if startdate == None or nextdate == None:
                    self.config.log('Error validating page for day:%s on npo.nl\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno, offset))
                    continue

                d = (startdate.split(',')[-1].strip()).split(' ')
                startdate = datetime.datetime.strptime('%s %s %s' % (d[0], d[1], d[2]),'%d %b %Y').date()

                d = (nextdate.split(',')[-1].strip()).split(' ')
                nextdate = datetime.datetime.strptime('%s %s %s' % (d[0], d[1], d[2]),'%d %b %Y').date()

                fetch_list = {}
                channel_cnt = 0
                for c in htmldata.findall('div/div/div/div/div/ul/li'):
                    channel_cnt += 1
                    if c.get('class') == None:
                        cname = c.find('a/div').tail.strip()

                    elif c.get('class') == 'ttv':
                        cname = c.find('div').tail.strip()

                    elif c.get('class') == 'rtv':
                        cname = c.find('div').tail.strip()

                    # We add the appropriate channels to the fetch list. Comparing our list with their list
                    if cname in self.channel_names.keys() and self.channel_names[cname] in self.channels.values():
                        for chanid, channel in self.channels.items():
                            if self.channel_names[cname] == channel:
                                fetch_list[channel] = chanid
                                break

                    if self.config.write_info_files:
                        if not str(channel_cnt) in self.all_channels or cname != self.all_channels[str(channel_cnt)]['name']:
                            if channel_cnt > 24:
                                self.config.infofiles.addto_detail_list(u'Channel %s is named %s' % (channel_cnt, cname))

                            else:
                                self.config.infofiles.addto_detail_list(u'Channel %s should be named %s and is named %s' % (channel_cnt, self.all_channels[str(channel_cnt)]['name'], cname))

            except:
                self.config.log(['Error validating page for day:%s on npo.nl\n' % (offset), traceback.format_exc()])
                continue

            try:
                day_offset = 0
                for h in htmldata.findall('div/div/div/div/div/table/tr'):
                    phour = int(h.get('data-hour'))
                    channel_cnt = 0
                    for c in h.findall('td'):
                        cclass = c.get('class')
                        if cclass == None or cclass == 'padder left' or cclass == 'padder right':
                            continue

                        elif cclass in ('red', 'blue', 'green', 'ttv', 'rtv',):
                            channel_cnt += 1
                            if not str(channel_cnt) in fetch_list.keys():
                                continue

                            chanid = fetch_list[str(channel_cnt)]
                            for p in c.findall('a'):
                                ptext = p.findtext('div[@class="description"]/div[@class="program-title"]','')
                                pshour = p.get('data-start-hour','')
                                psmin =p.get('data-start-minutes','')
                                pstart = p.findtext('div[@class="time"]','')
                                pehour = p.get('data-end-hour','')
                                pemin = p.get('data-end-minutes','')

                                for v in (ptext, pshour, psmin):
                                    if v == '':
                                        self.config.log('Unable to determin Title and/or Starttime')
                                        continue

                                tdict = self.functions.checkout_program_dict()
                                tdict['source'] = u'npo'
                                tdict['channelid'] = chanid
                                tdict['channel'] = self.config.channels[chanid].chan_name
                                tdict['detail_url'][self.proc_id] = self.get_url(href = p.get('href',''))
                                if tdict['detail_url'][self.proc_id] != '':
                                    pid = tdict['detail_url'][self.proc_id].split('/')[-1]
                                    tdict['prog_ID'][self.proc_id] = u'npo-%s' % pid.split('_')[-1]

                                # The Title
                                tdict['name'] = self.functions.empersant(ptext)

                                prog_time = datetime.time(int(pshour), int(psmin), 0 ,0 ,CET_CEST)
                                if day_offset == 0 and phour < 6:
                                    day_offset = 1

                                tdict['offset'] = offset + day_offset

                                if day_offset == 1:
                                    tdict['start-time'] = datetime.datetime.combine(nextdate, prog_time)

                                else:
                                    tdict['start-time'] = datetime.datetime.combine(startdate, prog_time)

                                # There seem to be regular gaps between the programs
                                # I asume they are commercials and in between talk.
                                prog_time = datetime.time(int(pehour), int(pemin), 0 ,0 ,CET_CEST)
                                if day_offset == 1 or int(pehour) < 6:
                                    tdict['stop-time'] = datetime.datetime.combine(nextdate, prog_time)

                                else:
                                    tdict['stop-time'] = datetime.datetime.combine(startdate, prog_time)

                                pgenre = p.get('data-genre','')
                                if pgenre in self.config.source_cattrans[self.proc_id].keys():
                                    tdict['genre'] = self.config.source_cattrans[self.proc_id][pgenre][0].capitalize()
                                    tdict['subgenre'] = self.config.source_cattrans[self.proc_id][pgenre][1].capitalize()

                                else:
                                    p = pgenre.split(',')
                                    if len(p) > 1 and p[0] in self.config.source_cattrans[self.proc_id].keys():
                                        tdict['genre'] = self.config.source_cattrans[self.proc_id][p[0]][0].capitalize()
                                        tdict['subgenre'] = self.config.source_cattrans[self.proc_id][p[0]][1].capitalize()

                                    else:
                                        tdict['genre'] = u'overige'

                                    if self.config.write_info_files and pgenre != '':
                                        self.config.infofiles.addto_detail_list(unicode('unknown npo.nl genre => ' + pgenre + ': ' + tdict['name']))

                                # and append the program to the list of programs
                                tdict = self.check_title_name(tdict)
                                with self.source_lock:
                                    self.program_data[chanid].append(tdict)

                        else:
                            # Unknown Channel class
                            pass

            except:
                self.config.log(traceback.format_exc())

            for chanid in self.channels.keys():
                self.day_loaded[chanid][offset] = True


        for chanid in self.channels.keys():
            with self.source_lock:
                for tdict in self.program_data[chanid]:
                    self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

            self.channel_loaded[chanid] = True
            self.parse_programs(chanid, 0, 'fill')
            self.config.channels[chanid].source_data[self.proc_id].set()
            if len(self.program_data) == 0:
                self.config.channels[chanid].source_data[self.proc_id].set()
                continue

            try:
                self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

            except:
                pass

# end npo_HTML

class horizon_JSON(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the horizon.tv json pages. Based on FetchData
    """
    def init_channels(self):
        self.url_channels = ''
        self.init_channel_source_ids()

    def init_json(self):

        self.json_by_id = {}
        self.jsondata = {}
        self.jsondict = {}

    def get_url(self, type = 'channels', channel = 0, start = 0, end = 0):

        horizon = 'https://www.horizon.tv/oesp/api/NL/nld/web/'

        if type == 'channels':
            return  u'%schannels/' % (horizon)

        elif type == 'day':
            return '%slistings?byStationId=%s&byStartTime=%s~%s&sort=startTime' % (horizon, channel, start, end)

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        # download the json feed
        total = self.config.fetch_func.get_page(self.get_url(), 'utf-8')
        if total == None:
            self.fail_count += 1
            self.config.log("Unable to get channel info from %s\n" % self.source)
            return 69  # EX_UNAVAILABLE

        channel_list = json.loads(total)

        # and create a file with the channels
        self.all_channels ={}
        for channel in channel_list['channels']:
            for schedule in channel['stationSchedules']:
                chanid = schedule['station']['id']
                self.all_channels[chanid] = {}
                self.all_channels[chanid]['name'] = self.functions.unescape(schedule['station']['title']).strip()
                if self.all_channels[chanid]['name'][-3:] == ' HD':
                    self.all_channels[chanid]['name'] = self.all_channels[chanid]['name'][:-3].strip()

                self.all_channels[chanid]['HD'] = schedule['station']['isHd']
                for icon in schedule['station']['images']:
                    if icon['assetType'] == 'station-logo-large' and icon['url'] != '':
                        icon = re.split('/', icon['url'])
                        #~ icon = '%s/%s/%s' % (icon[-3], icon[-2], icon[-1])
                        self.all_channels[chanid]['icon'] = icon[-1].split('?')[0]
                        break

    def load_pages(self):
        first_fetch = True
        if self.config.opt_dict['offset'] > 7:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        try:
            channel_cnt = 0
            for chanid in self.channels.keys():
                channel_cnt += 1
                page_count = 0
                if self.quit:
                    return

                channel = self.channels[chanid]
                # Maximum 100 programs are returned. So we try to get all and reset start to the endtime of the last
                #~ start = datetime.date.fromordinal(self.current_date + self.config.opt_dict['offset'])
                #~ start = int(time.mktime((start.year,start.month,start.day,0,0,0,0,0,-1)))*1000
                start = int(time.mktime(datetime.date.fromordinal(self.current_date + self.config.opt_dict['offset']).timetuple()))*1000
                end = start + (86400000 * self.config.opt_dict['days'])
                last_start = 0
                page_fail = 0
                while True:
                    if self.quit:
                        return

                    if end <= start or last_start == start:
                        break

                    last_start = start
                    page_count += 1
                    self.config.log(['\n', 'Now fetching %s(xmltvid=%s%s) from horizon.tv\n' % \
                        (self.config.channels[chanid].chan_name, self.config.channels[chanid].xmltvid, (self.config.channels[chanid].opt_dict['compat'] and '.tvgids.nl' or '')), \
                        '    (channel %s of %s) for %s days, page %s.\n' % \
                        ( channel_cnt, len(self.channels), self.config.opt_dict['days'], page_count)], 2)

                    channel_url = self.get_url('day', channel, start, end)
                    if not first_fetch:
                        # be nice to horizon.tv
                        time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
                        first_fetch = false

                    # get the raw programming for the day
                    strdata = self.config.fetch_func.get_page(channel_url, 'utf-8')
                    if strdata == None or strdata.replace('\n','') == '{}':
                        self.config.log("No data on horizon.tv channel %s page=%d\n" % (self.config.channels[chanid].chan_name, page_count))
                        self.fail_count += 1
                        page_fail += 1
                        last_start = start-1
                        if page_fail == 3:
                            break

                        page_count -= 1
                        continue

                    # Just let the json library parse it.
                    program_list = json.loads(strdata)
                    self.base_count += 1
                    for item in program_list['listings']:
                        if not 'program' in item:
                            continue

                        if item['program']['title'] == 'Zender verstrekt geen informatie':
                            start = end
                            break

                        if item['stationId'] != channel:
                            # Wrong channel
                            continue

                        tdict = self.functions.checkout_program_dict()
                        if (item['imi'] != '') and (item['imi'] != None):
                            tdict['prog_ID'][self.proc_id] = u'ho-%s' % (item['imi'][4:])
                            self.json_by_id[tdict['prog_ID'][self.proc_id]] = item
                            tdict['ID'] = tdict['prog_ID'][self.proc_id]

                        tdict['source'] = self.source
                        tdict['channelid'] = chanid
                        tdict['channel']  = self.config.channels[chanid].chan_name

                        # The Title
                        tdict['name'] = self.functions.unescape(item['program']['title'])
                        if  tdict['name'] == None or tdict['name'] == '':
                            self.config.log('Can not determine program title for "%s"\n' % tdict['detail_url'][self.proc_id])
                            continue

                        # The timing
                        tdict['start-time'] = datetime.datetime.fromtimestamp(int(item['startTime'])/1000, CET_CEST)
                        tdict['stop-time']  = datetime.datetime.fromtimestamp(int(item['endTime'])/1000, CET_CEST)
                        if tdict['start-time'] == None or tdict['stop-time'] == None:
                            continue

                        tdict['offset'] = self.functions.get_offset(tdict['start-time'])
                        start = item['endTime']
                        if 'secondaryTitle' in item['program'] \
                          and item['program']['secondaryTitle'][:27].lower() != 'geen informatie beschikbaar' \
                          and item['program']['secondaryTitle'] not in (item['program']['title']) \
                          and len(item['program']['secondaryTitle']) < 50:
                            tdict['titel aflevering'] = self.functions.unescape(item['program']['secondaryTitle'])

                        ep = int(item['program']['seriesEpisodeNumber']) if 'seriesEpisodeNumber' in item['program'] else 0
                        tdict['episode'] =  0 if ep > 1000 else str(ep)

                        shortdesc = self.functions.unescape(item['program']['shortDescription']) if 'shortDescription' in item['program'] else ''
                        tdict['description'] = self.functions.unescape(item['program']['description']) if 'description' in item['program'] else shortdesc
                        tdict['airdate'] = datetime.datetime.fromtimestamp(int(item['program']['airdate'])/1000, CET_CEST) if 'airdate' in item['program'] else ''
                        tdict['jaar van premiere'] = item['program']['year'] if 'year' in item['program'] else ''
                        tdict['rerun'] = ('latestBroadcastStartTime' in item['program'] and item['startTime'] != item['program']['latestBroadcastStartTime'])
                        if 'IMDb rating:' in tdict['description']:
                            d = re.split('IMDb rating:', tdict['description'])
                            tdict['description'] = d[0].strip()
                            tdict['star-rating'] = re.split('/', d[1])[0].strip()

                        if 'cast' in item['program'] and item['program']['cast'] != []:
                            tdict['credits']['actor'] = item['program']['cast']

                        if 'directors' in item['program'] and item['program']['directors'] != []:
                            tdict['credits']['director'] = item['program']['directors']

                        cats = item['program']['categories']
                        if 'mediaType' in item['program'] and item['program']['mediaType'] == 'FeatureFilm':
                            tdict['genre'] = 'film'

                            if len(cats) > 0:
                                tdict['subgenre'] = cats[-1]['title'].capitalize()

                        elif len(cats) == 0:
                            tdict['genre'] = 'overige'

                        elif len(cats) == 1 and (cats[0]['id'], ) in self.config.source_cattrans[self.proc_id].keys():
                            tdict['genre'] = self.config.source_cattrans[self.proc_id][(cats[0]['id'], )][0]
                            tdict['subgenre'] = self.config.source_cattrans[self.proc_id][(cats[0]['id'], )][1]

                        elif len(cats) == 2 and (cats[0]['id'], cats[1]['id']) in self.config.source_cattrans[self.proc_id].keys():
                            tdict['genre'] = self.config.source_cattrans[self.proc_id][(cats[0]['id'], cats[1]['id'])][0]
                            tdict['subgenre'] = self.config.source_cattrans[self.proc_id][(cats[0]['id'],cats[1]['id'])][1]

                        elif len(cats) == 2 and (cats[0]['id'], ) in self.config.source_cattrans[self.proc_id].keys():
                            tdict['genre'] = self.config.source_cattrans[self.proc_id][(cats[0]['id'], )][0]
                            if self.config.source_cattrans[self.proc_id][(cats[0]['id'], )][1] == '':
                                tdict['subgenre'] = cats[1]['title'].capitalize()
                                self.config.new_cattrans[self.proc_id][(cats[0]['id'], cats[1]['id'])] = \
                                        (self.config.source_cattrans[self.proc_id][(cats[0]['id'], )][0], unicode(cats[1]['title'].capitalize()))
                                if self.config.write_info_files:
                                    ids ="("
                                    titles = "("
                                    for c in cats:
                                        ids = "%s'%s', " % (ids, c['id'])
                                        titles = "%s'%s', " % (titles, c['title'].capitalize())
                                    ids = ids[:-2] + ")"
                                    titles = titles[:-2] + ")"
                                    self.config.infofiles.addto_detail_list(unicode('new horizon subcategorie => ' + ids + ': ' + titles + ', '))

                            else:
                                tdict['subgenre'] = self.config.source_cattrans[self.proc_id][(cats[0]['id'], )][1]

                        else:
                            tdict['genre'] = unicode(cats[0]['title'].capitalize())
                            if len(cats) == 2:
                                tdict['subgenre'] = unicode(cats[1]['title'].capitalize())
                                self.config.new_cattrans[self.proc_id][(cats[0]['id'], cats[1]['id'])] = \
                                        (unicode(cats[0]['title'].capitalize()), unicode(cats[1]['title'].capitalize()))

                            else:
                                self.config.new_cattrans[self.proc_id][(cats[0]['id'],)] = unicode(cats[0]['title'].capitalize(), u'')

                            if self.config.write_info_files:
                                ids ="("
                                titles = "("
                                for c in cats:
                                    ids = "%s'%s', " % (ids, c['id'])
                                    titles = "%s'%s', " % (titles, c['title'].capitalize())
                                ids = ids[:-2] + ")"
                                titles = titles[:-2] + ")"
                                self.config.infofiles.addto_detail_list(unicode('new horizon categorie => ' + ids + ': ' + titles + ', '))

                        if self.config.write_info_files:
                            for cat in cats:
                                self.config.infofiles.addto_detail_list(u'horizon categorie: %s => %s' %(cat['id'], cat['title'].capitalize()))

                        self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict
                        tdict = self.check_title_name(tdict)
                        with self.source_lock:
                            self.program_data[chanid].append(tdict)

                    if int(program_list['entryCount']) < 100:
                        break

                with self.source_lock:
                    for tdict in self.program_data[chanid]:
                        self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict


                # If all went well or it's the last try we set them loaded
                self.channel_loaded[chanid] = True
                self.parse_programs(chanid, 0, 'None')
                self.config.channels[chanid].source_data[self.proc_id].set()

                try:
                    self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                except:
                    pass

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread:\n' %  (self.source), traceback.format_exc()], 0)

            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()
            return None

# end horizon_JSON

class humo_JSON(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the tvgids.nl json pages. Based on FetchData
    """
    def init_channels(self):

        self.init_channel_source_ids()
        self.chanids = {}
        for chanid, sourceid in self.channels.items():
            self.chanids[sourceid] = chanid

    def init_json(self):

        self.json_by_id = {}
        self.jsondata = {}
        self.jsondict = {}

    def get_url(self, channels = 'channels', offset = 0):

        base_url = 'http://www.humo.be'
        base_json = base_url + '/api/epg/humosite'
        scan_day = datetime.date.fromordinal(self.current_date + offset).strftime("%Y-%m-%d")

        if channels == 'channels':
            return  u'%s/channels' % (base_json)

        elif channels == 'main':
            return '%s/schedule/main/%s/full' % (base_json, scan_day)

        elif channels == 'rest':
            return '%s/schedule/rest/%s/full' % (base_json, scan_day)

        else:
            return '%s/schedule/%s/%s/full' % (base_json, channels, scan_day)

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        # download the json feed
        total = self.config.fetch_func.get_page(self.get_url(), 'utf-8')
        if total == None:
            self.fail_count += 1
            self.config.log("Unable to get channel info from %s\n" % self.source)
            return 69  # EX_UNAVAILABLE

        channel_list = json.loads(total)

        # and create a file with the channels
        self.all_channels ={}
        for chan_grp in channel_list['groups']:
            grp_name = chan_grp['name']
            grp_code = chan_grp['code']
            for channel in chan_grp['broadcasters']:
                chanid = unicode(channel['id'])
                icon = channel['media'][0]['resized_urls']['small']
                icon = icon.split('/')
                self.all_channels[chanid] = {}
                self.all_channels[chanid]['name'] = channel['display_name']
                self.all_channels[chanid]['icon'] = icon[-1]
                self.all_channels[chanid]['fetch_grp'] = grp_code

    def load_pages(self):

        if self.config.opt_dict['offset'] > 7:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        first_fetch = True
        try:
            for offset in range(self.config.opt_dict['offset'], min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 8)):
                rest_channels = self.chanids.keys()
                for retry in (('main', 1), ('rest', 1), ('main', 2), ('rest', 2)):
                    if self.quit:
                        return

                    # Check if it is already loaded
                    channel_url = self.get_url(retry[0], offset)
                    if len(rest_channels) == 0:
                        continue

                    self.config.log(['\n', 'Now fetching %s channels from humo.be\n' % retry[0], \
                        '    (day %s of %s).\n' % (offset, self.config.opt_dict['days'])], 2)

                    if not first_fetch:
                        # be nice to humo.be
                        time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
                        first_fetch = False

                    # get the raw programming for the day
                    strdata = self.config.fetch_func.get_page(channel_url, 'utf-8')
                    if strdata == None or strdata.replace('\n','') == '{}':
                        self.config.log("No data on humo.be %s-page for day=%d attempt %s\n" % (retry[0], offset, retry[1]))
                        self.fail_count += 1
                        continue

                    # Just let the json library parse it.
                    self.base_count += 1
                    self.day_loaded[0][offset] = True
                    jsondata = json.loads(strdata)
                    for channel in jsondata["broadcasters"]:
                        chan_scid = unicode(channel['id'])
                        if chan_scid in rest_channels:
                            chanid = self.chanids[chan_scid]
                            rest_channels.remove(chan_scid)

                        else:
                            continue

                        for item in channel['events']:
                            tdict = self.functions.checkout_program_dict()
                            if (item['id'] != '') and (item['id'] != None):
                                tdict['prog_ID'][self.proc_id] = u'humo-%s' % (item['id'])
                                self.json_by_id[tdict['prog_ID'][self.proc_id]] = item
                                tdict['ID'] = tdict['prog_ID'][self.proc_id]

                            tdict['source'] = self.source
                            tdict['channelid'] = chanid
                            tdict['channel']  = self.config.channels[chanid].chan_name
                            tdict['detail_url'][self.proc_id] = item['url']

                            # The Title
                            tdict['name'] = self.functions.unescape(item['program']['title'])
                            if  tdict['name'] == None or tdict['name'] == '':
                                self.config.log('Can not determine program title for "%s"\n' % tdict['detail_url'][self.proc_id])
                                continue

                            # The timing
                            tdict['start-time'] = datetime.datetime.fromtimestamp(item['starttime'], CET_CEST)
                            tdict['stop-time']  = datetime.datetime.fromtimestamp(item['endtime'], CET_CEST)
                            if tdict['start-time'] == None or tdict['stop-time'] == None:
                                continue

                            tdict['offset'] = self.functions.get_offset(tdict['start-time'])
                            if 'content_long' in item['program'].keys():
                                tdict['description'] = item['program']['content_long']

                            elif 'content_short' in item['program'].keys():
                                tdict['description'] = item['program']['content_short']

                            elif 'description' in item['program'].keys():
                                tdict['description'] = item['program']['description']

                            if 'episodetitle' in item['program'].keys():
                                tdict['titel aflevering'] = item['program']['episodetitle']

                            if 'episodenumber' in item['program'].keys():
                                tdict['episode'] = item['program']['episodenumber']

                            if 'episodeseason' in item['program'].keys():
                                tdict['season'] = item['program']['episodeseason']

                            if 'year' in item['program'].keys():
                                tdict['jaar van premiere'] = item['program']['year']

                            if 'countries' in item['program'].keys():
                                #~ tdict['country'] = item['program']['countries']
                                for cstr in item['program']['countries']:
                                    cstr = cstr.upper().strip()
                                    if '(' in cstr:
                                        cstr = cstr.split('(')[1][:-1]

                                    if cstr in self.config.coutrytrans.values():
                                        tdict['country'] = cstr
                                        break

                                    elif cstr in self.config.coutrytrans.keys():
                                        tdict['country'] = self.config.coutrytrans[cstr]
                                        break

                                    elif self.config.write_info_files:
                                        self.config.infofiles.addto_detail_list(u'new country => %s' % (cstr))

                            if 'credits' in item['program'].keys():
                                for role in item['program']['credits']:
                                    if not role['role'] in tdict['credits']:
                                        tdict['credits'][role['role']] = []

                                    if not self.functions.unescape(role['name']) in tdict['credits'][role['role']]:
                                        tdict['credits'][role['role']].append(self.functions.unescape(role['name']))

                            if 'genres' in item['program'].keys():
                                if item['program']['genres'][0] in self.config.source_cattrans[self.proc_id].keys() and \
                                  self.config.source_cattrans[self.proc_id][item['program']['genres'][0]] != [u'Overige', u'']:
                                    tdict['genre'] = self.config.source_cattrans[self.proc_id][item['program']['genres'][0]][0]
                                    tdict['subgenre'] = self.config.source_cattrans[self.proc_id][item['program']['genres'][0]][1]

                                else:
                                    for g in  self.config.source_cattrans[self.proc_id].keys():
                                        if g == item['program']['genres'][0][0:len(g)]:
                                            tdict['genre'] = g
                                            sub = '' if len(item['program']['genres'][0]) <= len(g)+1 else item['program']['genres'][0][len(g)+1:]
                                            tdict['subgenre'] = sub
                                            self.config.new_cattrans[self.proc_id][item['program']['genres'][0]] = (g, sub)
                                            break

                                    else:
                                        tdict['genre'] = 'Overige'
                                        self.config.new_cattrans[self.proc_id][item['program']['genres'][0]] = (u'Overige', u'')
                                        if self.config.write_info_files:
                                            for gstr in item['program']['genres']:
                                                self.config.infofiles.addto_detail_list('new humo genre => ' + gstr)

                            else:
                                tdict['genre'] = 'Overige'

                            if 'teletext' in item['properties'].keys() and item['properties']['teletext'] == 1:
                                tdict['teletekst']  = True

                            if 'dolby' in item['properties'].keys() and item['properties']['dolby'] == 1:
                                tdict['audio']  = 'dolby'

                            if 'prop_16_9' in item['properties'].keys() and item['properties']['prop_16_9'] == 1:
                                tdict['video']['breedbeeld']  = True

                            if 'hd' in item['properties'].keys() and item['properties']['hd'] == 1:
                                tdict['video']['HD'] = True

                            if 'repeat' in item['properties'].keys() and item['properties']['repeat'] == 1:
                                tdict['rerun']  = True

                            if 'final' in item['properties'].keys() and item['properties']['final'] == 1:
                                tdict['last-chance']  = True

                            if 'new' in item['properties'].keys() and item['properties']['new'] == 1:
                                tdict['new']  = True

                            if self.config.write_info_files:
                                for key in item['properties'].keys():
                                    if not key in ('live', 'repeat', 'final', 'new', 'hd', 'prop_16_9', 'teletext', 'issub', 'dolby', \
                                      'part_of_series', 'series_id', 'maintitle', 'pdc', 'eventduration', 'selection'):
                                        self.config.infofiles.addto_detail_list('new humo property => %s=%s'  % (key, item['properties'][key]))

                                for key in item['program'].keys():
                                    if not key in ('id', 'external_id', 'title', 'media', 'twitterhashtag', 'youtubeid', 'website', \
                                      'programduration', 'episodetitle', 'episodenumber', 'episodeseason', 'episodetotal', \
                                      'description', 'content_short', 'content_long', 'year', 'countries', 'credits', 'genres', \
                                      'opinion'):
                                      #~ 'opinion', 'appreciation'):
                                        self.config.infofiles.addto_detail_list('new humo programitem => %s=%s' % (key, item['program'][key]))

                            tdict = self.check_title_name(tdict)
                            self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict
                            with self.source_lock:
                                self.program_data[chanid].append(tdict)

            for chanid in self.channels.keys():
                self.program_data[chanid].sort(key=lambda program: (program['start-time'],program['stop-time']))
                self.parse_programs(chanid, 0, 'None')
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()
                try:
                    self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                except:
                    pass

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread:\n' %  (self.source), traceback.format_exc()], 0)

            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()
            return None

# end humo_JSON

class vpro_HTML(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the vpro.nl page. Based on FetchData Class
    """
    def init_channels(self):
        """ General Site layout
        """

        # These regexes fetch the relevant data out of the vpro.nl pages, which then will be parsed to the ElementTree
        self.available_dates = re.compile('<div class="epg-available-days">(.*?)</div>',re.DOTALL)
        self.fetch_channellist = re.compile('<ul class="epg-channel-names">(.*?)</ul>',re.DOTALL)
        self.fetch_titels = re.compile('<h6 class="title">(.*?)</h6>',re.DOTALL)
        self.fetch_data = re.compile('<section class="section-with-layout component-theme theme-white">(.*?)</section>',re.DOTALL)
        self.fetch_genre_codes = re.compile("(g[0-9]+)")
        self.fetch_descr_parts = re.compile("(.*?[\.:]+ |.*?[\.:]+\Z)")

        self.fetch_subgenre = re.compile('^(.*?) uit (\d{4}) van (.*?)(over .*?\.|waarin .*?\.|voor .*?\.|\.)')
        self.fetch_subgenre2 = re.compile('^([A-Z/]+) (\d{4})\. ?(.*?) van (.*?)\.')
        self.fetch_subgenre3 = re.compile('^(.*?) uit (\d{4})')
        self.fetch_subgenre4 = re.compile('^(.*?) (naar|waarin|over).*?')

        self.init_channel_source_ids()
        self.availabe_days = []
        self.chanids = {}
        for chanid, sourceid in self.channels.items():
            self.chanids[sourceid] = chanid

    def get_url(self, offset = None):

        vpro_base = 'http://www.vpro.nl/epg-embeddable'
        if offset == None:
            return u'%s.html' % (vpro_base)

        elif isinstance(offset, int):
            scan_date = datetime.date.fromordinal(self.current_date + offset)
            return u'%s/content/0.html?day=%s' % (vpro_base,  scan_date.strftime('%Y-%m-%d'))

    def get_channels(self):

        try:
            strdata = self.config.fetch_func.get_page(self.get_url())
            strdata = self.functions.clean_html(strdata)
            if strdata == None:
                self.fail_count += 1
                self.config.log(["Unable to get channel info from %s\n" % self.source])
                return 69  # EX_UNAVAILABLE

            self.get_available_days(strdata)
            self.get_channel_lineup(strdata)

        except:
            self.fail_count += 1
            self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
            return 69  # EX_UNAVAILABLE

    def get_channel_lineup(self, htmldata):
        chan_list = []
        channel_cnt = 0
        strdata = self.fetch_channellist.search(htmldata).group(1)
        htmldata = ET.fromstring( (u'<root>\n' + strdata + u'\n</root>\n').encode('utf-8'))
        for c in htmldata.findall('li'):
            channel_cnt+=1
            name = self.functions.empersant(c.text)
            scid =re.sub('[ /]', '_', name.lower())
            scid =re.sub('é', 'e', scid)
            scid =re.sub('[!(),]', '', scid)
            #~ scid = '%s-%s' % (self.proc_id, scid)
            if c.attrib['class'] == "epg-source-radio epg-channel-name":
                grp = 11

            else:
                grp = 99

            self.all_channels[scid] = {}
            self.all_channels[scid]['name'] = name
            self.all_channels[scid]['group'] = grp
            chan_list.append(scid)

        return chan_list

    def get_available_days(self, htmldata):
        self.availabe_days = []
        htmldata = self.available_dates.search(htmldata).group(1)
        htmldata = ET.fromstring( (htmldata).encode('utf-8'))
        for c in htmldata.findall('li/a'):
            d = re.split('-', c.attrib['rel'])
            self.availabe_days.append(datetime.date(int(d[0]), int(d[1]), int(d[2])).toordinal() - self.current_date)

    def load_pages(self):
        # The vpro description has all kind of inden info like: year episode, cast, presentation.
        def filter_desc(tdict):
            if tdict['description'] == '':
                return

            desc_items = self.get_string_parts(tdict['description'], ('met oa',))
            for di, dt in desc_items.items():
                if len(dt) == 0:
                    continue

                # Get subgenre, and possibly jaar van premiere, regisseur, country
                if di == 'start':
                    subg = self.fetch_subgenre.search(dt[0])
                    subg2 = self.fetch_subgenre2.search(dt[0])
                    subg3 = self.fetch_subgenre3.search(dt[0])
                    subg4 = self.fetch_subgenre4.search(dt[0])
                    if subg != None:
                        tdict['subgenre'] = subg.group(1)
                        tdict['jaar van premiere'] = subg.group(2)
                        direct = re.sub(' en ',  ' , ', subg.group(3))
                        direct = re.split(',', direct)
                        if not 'director' in tdict['credits']:
                            tdict['credits']['director'] = []

                        for d in direct:
                            tdict['credits']['director'].append(d)

                    elif subg2 != None:
                        cstr = re.split('/', subg2.group(1))
                        for c in cstr:
                            if c in self.config.coutrytrans.values():
                                tdict['country'] = c
                                break

                            elif c in self.config.coutrytrans.keys():
                                tdict['country'] = self.config.coutrytrans[c]
                                break

                            elif self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(u'new country => %s' % (c))

                        tdict['jaar van premiere'] = subg2.group(2)
                        tdict['subgenre'] = subg2.group(3)
                        direct = re.sub(' en ',  ' , ', subg2.group(4))
                        direct = re.split(',', direct)
                        if not 'director' in tdict['credits']:
                            tdict['credits']['director'] = []

                        for d in direct:
                            dtest = re.split(' ', d)
                            if dtest[0] in ('gebaseerd', 'naar', ) or len(dtest) > 5:
                                continue

                            tdict['credits']['director'].append(d)

                    elif subg3 != None:
                        tdict['subgenre'] = subg3.group(1)
                        tdict['jaar van premiere'] = subg3.group(2)

                    elif dt[0][0:3] == 'Afl' or dt[0][0:7] == 'Overige':
                        pass

                    elif subg4 != None:
                        subg5 = re.split(' ', subg4.group(1))
                        if len(subg5) <= 4:
                            tdict['subgenre'] = subg4.group(1)

                    else:
                        subg6 = re.split(' ', dt[0])
                        if len(subg6) <= 4:
                            tdict['subgenre'] = dt[0]


                # Get any roles
                elif di in self.config.roletrans.keys():
                    role = self.config.roletrans[di]
                    if not role in tdict['credits']:
                        tdict['credits'][role] = []

                    cast = re.sub('e\.a\.',  '', dt[0])
                    cast = re.sub(' en ',  ' , ', cast)
                    cast = re.split(',', cast)
                    for cn in cast:
                        tdict['credits'][role].append(cn.split('(')[0].strip())

                # Get the episode Number
                elif di == 'aflevering':
                    ep = re.search('[0-9]+', dt[0])
                    if ep != None:
                        tdict['episode'] = int(ep.group(0))

                # Get the subtitle and possibly an episode number
                elif di[0:3] == 'afl':
                    tdict['titel aflevering'] = dt[0].strip()
                    ep = re.search('[0-9]+', di)
                    if ep != None and tdict['episode'] == 0:
                        tdict['episode'] = int(ep.group(0))

                elif di[0:9] == 'vertaling':
                    pass

                elif di not in ('met oa', ) and self.config.write_info_files:
                    self.config.infofiles.addto_detail_list(u'new vpro descr item => %s' % (di))

            # Alternative Acters list
            if 'met oa' in desc_items and not 'met'in desc_items:
                role = self.config.roletrans['met']
                if not role in tdict['credits']:
                    tdict['credits'][role] = []

                cast = re.sub(' en ',  ' , ', desc_items['met oa'][0])
                cast = re.split(',', cast)
                for cn in cast:
                    tdict['credits'][role].append(cn.split('(')[0].strip())

        def get_programs(xml, chanid):
            try:
                tdict = None
                day_offset = 0
                for p in xml.findall('li'):
                    ptext = p.get('data-title')
                    if ptext == None:
                        # No title Found
                        continue

                    ptime = p.findtext('div[@class="content"]/div[@class="meta"]')
                    if ptime == None:
                        # No start-stop time Found
                        continue

                    tdict = self.functions.checkout_program_dict()
                    tdict['source'] = u'vpro'
                    tdict['channelid'] = chanid
                    tdict['channel'] = self.config.channels[chanid].chan_name
                    tdict['detail_url'][self.proc_id] = p.get('data-read-more-url', '')
                    #~ if tdict['detail_url'][self.proc_id] != '':
                        #~ pid = tdict['detail_url'][self.proc_id].split('/')[-1]
                        #~ tdict['prog_ID'][self.proc_id] = u'npo-%s' % pid.split('_')[-1]

                    # The Title
                    tdict['name'] = self.functions.empersant(ptext.strip())

                    pstart = re.sub('vpro', '', ptime).strip()
                    pstart = pstart.split(':')
                    prog_time = datetime.time(int(pstart[0]), int(pstart[1]), 0 ,0 ,CET_CEST)
                    if day_offset == 0 and int(pstart[0]) < 6:
                        day_offset = 1

                    tdict['offset'] = offset + day_offset

                    if day_offset == 1:
                        tdict['start-time'] = datetime.datetime.combine(nextdate, prog_time)

                    else:
                        tdict['start-time'] = datetime.datetime.combine(startdate, prog_time)

                    tdict['description'] = self.functions.empersant(p.get('data-description','').strip())
                    omroep = p.findtext('div[@class="content"]/h6[@class="title"]/span[@class="broadcaster"]')
                    if not omroep in ('', None):
                        tdict['omroep'] = self.functions.empersant(omroep)

                    pgenre = p.get('class','')
                    pg = self.fetch_genre_codes.findall(pgenre)
                    if len(pg) > 0:
                        pg = tuple(pg)
                        if len(pg) > 2:
                            pg = pg[0:2]

                        if pg in self.config.source_cattrans[self.proc_id].keys():
                            tdict['genre'] = self.config.source_cattrans[self.proc_id][pg][0].capitalize()
                            tdict['subgenre'] = self.config.source_cattrans[self.proc_id][pg][1].capitalize()

                        else:
                            if len(pg) > 1 and (pg[0].lower(), ) in self.config.source_cattrans[self.proc_id].keys():
                                tdict['genre'] = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )][0].capitalize()
                                tdict['subgenre'] = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )][1].capitalize()
                                self.config.new_cattrans[self.proc_id][(pg[0], pg[1])] = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )]

                            else:
                                tdict['genre'] = u'overige'
                                if len(pg) == 2:
                                    tdict['subgenre'] = pg[1].capitalize()
                                    self.config.new_cattrans[self.proc_id][pg] = (u'Overige', pg[1])

                                elif not pgenre in ('', 'gvpro'):
                                    self.config.new_cattrans[self.proc_id][pg] = (u'Overige', u'')

                            if self.config.write_info_files and not pgenre in ('', 'gvpro'):
                                self.config.infofiles.addto_detail_list(unicode('unknown vpro.nl genre => ' + pgenre + ': ' + tdict['name']))

                    else:
                        tdict['genre'] = u'overige'

                    filter_desc(tdict)
                    # and append the program to the list of programs
                    tdict = self.check_title_name(tdict)
                    with self.source_lock:
                        self.program_data[chanid].append(tdict)

            except:
                self.config.log(traceback.format_exc())

        if self.config.opt_dict['offset'] > 5:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        for retry in (0, 1):
            for offset in range(self.config.opt_dict['offset'], min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 5)):
                if self.quit:
                    return

                # Check if it is already loaded
                if self.day_loaded[0][offset]:
                    continue

                if len(self.availabe_days) > 0 and not offset in self.availabe_days:
                    continue

                self.config.log(['\n', 'Now fetching %s channels from vpro.nl\n' % (len(self.channels)), \
                    '    (day %s of %s).\n' % (offset, self.config.opt_dict['days'])], 2)

                channel_url = self.get_url(offset)

                # get the raw programming for the day
                strdata = self.config.fetch_func.get_page(channel_url)
                if strdata == None or 'We hebben deze pagina niet gevonden...' in strdata:
                    self.config.log("No data on vpro.nl for day=%d\n" % (offset))
                    self.fail_count += 1
                    continue

                try:
                    strdata = self.functions.clean_html(strdata)
                    if len(self.availabe_days) == 0:
                        self.get_available_days(strdata)
                        lineup = self.get_channel_lineup(strdata)

                    strdata = self.fetch_data.search(strdata).group(0)
                    noquote = strdata
                    for t in self.fetch_titels.findall(strdata):
                        t = re.sub('<span class="broadcaster">(.*?)</span>', '', t)
                        t = t.strip()
                        tt = t
                        for s in (('"', '&quot;'), ('<', '&lt;'), ('>', '&gt;')):
                            if s[0] in t:
                                tt = re.sub(s[0], s[1], tt)
                                t = re.sub('\?', '\\?', t)
                                t = re.sub('\*', '\\*', t)
                                t = re.sub('\+', '\\+', t)

                        if t != tt:
                            noquote = re.sub(t, tt, noquote, flags = re.IGNORECASE)

                    htmldata = ET.fromstring( noquote.encode('utf-8'))

                except:
                    self.config.log('Error extracting ElementTree for day:%s on vpro.nl\n' % (offset))
                    self.fail_count += 1
                    if self.config.write_info_files:
                        self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                        self.config.infofiles.write_raw_string(noquote)

                    continue

                # First we get the line-up and some date checks
                self.base_count += 1
                try:
                    startdate = htmldata.find('div[@class="grid"]/div/div').get('data-selected-guide-date')
                    if startdate == None:
                        self.config.log('Error validating page for day:%s on vpro.nl\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno, offset))
                        continue

                    d = startdate.split('-')
                    startdate = datetime.date(int(d[0]), int(d[1]), int(d[2]))
                    nextdate = startdate + datetime.timedelta(days=1)
                    if startdate.toordinal() - self.current_date != offset:
                        self.config.log('Error validating page for day:%s on vpro.nl\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno, offset))
                        continue

                except:
                    self.config.log(traceback.format_exc())
                    continue

                try:
                    channel_cnt = 0
                    for c in htmldata.findall('div[@class="grid"]/div/div/div/div/div/div[@class="epg-channels-container"]/ol'):
                        scid = lineup[channel_cnt]
                        channel_cnt += 1
                        if not scid in self.chanids.keys():
                            continue

                        chanid = self.chanids[scid]
                        get_programs(c, chanid)
                        if channel_cnt == 2:
                            self.day_loaded[chanid][offset] = True

                except:
                    self.config.log(traceback.format_exc())

                # be nice to npo.nl
                self.day_loaded[0][offset] = True
                time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))

        for chanid in self.channels.keys():
            self.channel_loaded[chanid] = True
            if len(self.program_data[chanid]) == 0:
                self.config.channels[chanid].source_data[self.proc_id].set()
                continue

            # Add starttime of the next program as the endtime
            with self.source_lock:
                self.program_data[chanid].sort(key=lambda program: (program['start-time']))
                self.add_endtimes(chanid, 6)

                for tdict in self.program_data[chanid]:
                    self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

            self.parse_programs(chanid, 0, 'none')
            self.config.channels[chanid].source_data[self.proc_id].set()

            try:
                self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

            except:
                pass

# end vpro_HTML

class nieuwsblad_HTML(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the nieuwsblad.be page. Based on FetchData Class
    """
    def init_channels(self):
        """ General Site layout
            <html class="no-js " dir="ltr" lang="nl-BE">
                <head>
                <body class="theme-default" itemscope itemtype="http://schema.org/WebPage">
                    <div class="body-wrapper">
                        <div class="site-container">
                            <div class="site-container__inner">
                                <main role="main">
                                    <!-- start zone Zone_0 -->
                                    <section class="l-zone">
                                        <div class="grid">
                                            # Datedefinition
                                            <div class="grid__col">
                                                <div class="grid__col__inner">
                                                <!-- start block 'tvgids-top' -->
                                                    <div data-mht-block="zone_0__tvgids-top">
                                                        <div class="grid__col size-2-3--bp4">
                                                            <div class="grid__col__inner">
                                                                <h1>
                                                                    TV-Gids vandaag</h1>
                                                            </div>
                                                        </div>
                                                        <div class="grid__col size-1-3--bp4">
                                                            <div class="grid__col__inner">
                                                                <p>
                                                                    dinsdag, 01 september 2015</p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                <!-- end block 'tvgids-top' -->
                                                </div>
                                            </div>
                                            # Program list
                                            <div class="grid__col size-4-5">
                                                <div class="grid__col__inner">
                                                <!-- start block 'tvgids-left-center' -->
                                                    <div data-mht-block="zone_0__tvgids-left-center">
                                                        <div class="grid channel-block">
                                                            <div class="grid__col size-1-3--bp4">
                                                                <div class="grid__col__inner">
                                                                    <div class="tv-guide__channel">
                                                                        <h6>
                                                                            <img src="http://2.nieuwsbladcdn.be/extra/assets/img/tvgids/een.png" class="channelLogo" alt="EEN"
                                                                                  ><a href="http://www.nieuwsblad.be/tv-gids/een/gisteren">EEN</a>
                                                                        </h6>
                                                                    </div>
                                                                    <div class="program">
                                                                        <div class="time">09:00</div>
                                                                        <div class="title"><a href="http://www.nieuwsblad.be/tv-gids/een/gisteren/zomerbeelden">Zomerbeelden</a></div>
                                                                    </div>
                                                                        ...
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                <!-- end block 'tvgids-left-center' -->
                                                </div>
                                            </div>
                                            # Channel list
                                            <div class="grid__col size-1-5--bp4">
                                                <div class="grid__col__inner">
                                                <!-- start block 'tvgids-right-center' -->
                                                    <div data-mht-block="zone_0__tvgids-right-center">
                                                        <h3 class="heading">
                                                            Alle zenders</h3>
                                                        <div id="accordion" class="accordion" data-accordion data-jq-plugin="accordion">
                                                            <div class="accordion__header">
                                                                Vlaams</div>
                                                            <div class="accordion__content">
                                                                <a href="http://www.nieuwsblad.be/tv-gids/vandaag/0"><div class="channel-row">

                                                                    <img class="tv-icon" data-slug="EEN" src="http://2.nieuwsbladcdn.be/extra/assets/img/tvgids/een.png" onerror="this.onerror=null;this.src='http://2.nieuwsbladcdn.be/extra/assets/img/tvgids/dummy-channel.png';" data-lang="Vlaams" title="EEN">

                                                                    <img class="tv-icon" data-slug="VTM" src="http://2.nieuwsbladcdn.be/extra/assets/img/tvgids/vtm.png" onerror="this.onerror=null;this.src='http://2.nieuwsbladcdn.be/extra/assets/img/tvgids/dummy-channel.png';" data-lang="Vlaams" title="VTM">

                                                                    <img class="tv-icon" data-slug="VIER" src="http://2.nieuwsbladcdn.be/extra/assets/img/tvgids/vier.png" onerror="this.onerror=null;this.src='http://2.nieuwsbladcdn.be/extra/assets/img/tvgids/dummy-channel.png';" data-lang="Vlaams" title="VIER">
                                                                    </div>
                                                                </a>
                                                                    ...
                                                            </div>
                                                        </div>
                                                    </div>
                                                <!-- end block 'tvgids-right-center' -->
                                                </div>
                                            </div>
                                        </div>
                                    </section>
                                    <!-- end zone Zone_0 -->
                                </main>
                            </div>
                        </div>
                    </div>
                </body>
            </html>
        """

        # These regexes fetch the relevant data out of the nieuwsblad.be pages, which then will be parsed to the ElementTree
        self.getchannels = re.compile("<div class=\"grid channel__overview\">(.*?)<!-- end block 'tv-gids-channel-overview' -->",re.DOTALL)
        self.getheader = re.compile("<!-- start block 'tvgids-top' -->(.*?)<!-- end block 'tvgids-top' -->",re.DOTALL)
        self.getprograms = re.compile("<!-- start block 'tvgids-left-center' -->(.*?)<!-- end block 'tvgids-left-center' -->",re.DOTALL)
        self.getchannelgroups = re.compile("<div id=\"accordion\" class=\"accordion\" data-accordion data-jq-plugin=\"accordion\">(.*?)<!-- end block 'tvgids-right-center' -->",re.DOTALL)

        self.init_channel_source_ids()

    def get_url(self, channel = None, offset = 0, chan_group = 0):

        base_url = 'http://www.nieuwsblad.be/tv-gids'
        scan_day = self.config.weekdagen[int(datetime.date.fromordinal(self.current_date + offset).strftime("%w"))]
        if channel == 'base':
            return base_url

        elif channel == 'zenders':
            return '%s/zenders' % base_url

        elif channel != None:
            return '%s/%s/%s' % (base_url, channel,  scan_day)

        else:
            return u'%s/%s/%s' % (base_url,  scan_day, chan_group)

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        try:
            strdata = self.config.fetch_func.get_page(self.get_url('base'))
            if self.get_channel_lineup(strdata) == 69:
                self.fail_count += 1
                self.config.log(["Unable to get channel info from %s\n" % self.source])
                return 69  # EX_UNAVAILABLE

        except:
            self.fail_count += 1
            self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
            return 69  # EX_UNAVAILABLE

    def get_channel_lineup(self, chandata):

        chan_groups = {'Vlaams': 2,
                                    'Nederlands': 1,
                                    'Frans': 5,
                                    'Duits': 4,
                                    'Engels': 3,
                                    'Overige': 99}

        self.chan_names = {}
        self.page_strings = {}
        try:
            strdata = self.config.fetch_func.get_page(self.get_url('zenders'))
            if strdata == None:
                self.fail_count += 1

            else:
                strdata = self.getchannels.search(strdata).group(1)
                strdata = re.sub('<img (.*?)"\s*>', '<img \g<1>"/>', strdata)
                strdata = self.functions.clean_html('<div><div>' + strdata).encode('utf-8')
                htmldata = ET.fromstring(strdata)

                for item in htmldata.findall('div/div[@class]/div[@class="grid__col__inner"]/a[@href]'):
                    url = item.get('href', '')
                    if url != '':
                        chanid = url.split('/')[-2].strip()
                        if chanid in self.all_channels:
                            continue

                        name = self.functions.empersant(item.findtext('div[@class="grid"]/div[@class="grid__col"]/div[@class]/p')).strip()
                        icon = item.find('div[@class="grid"]/div[@class="grid__col size-1-3"]/div[@class]/img').get('src', '')
                        if icon != '':
                            icon = icon.split('/')
                            icon = '%s/%s' % (icon[-2], icon[-1])

                        self.all_channels[chanid] = {}
                        self.all_channels[chanid]['name'] = name
                        self.all_channels[chanid]['icon'] = icon
                        self.all_channels[chanid]['icongrp'] = 8
                        self.chan_names[name] = chanid

                for item in htmldata.findall('div/div[@class]/div[@class="grid__col__inner"]/div[@class="grid"]/a[@href]'):
                    url = item.get('href', '')
                    if url != '':
                        chanid = url.split('/')[-2]
                        if chanid in self.all_channels:
                            continue

                        name = self.functions.empersant(item.findtext('div[@class]/div[@class="grid__col__inner"]/p')).strip()
                        icon = item.find('div[@class]/div[@class="grid__col__inner"]/img').get('src', '')
                        if icon != '':
                            icon = icon.split('/')
                            icon = '%s/%s' % (icon[-2], icon[-1])

                        self.all_channels[chanid] = {}
                        self.all_channels[chanid]['name'] = name
                        self.all_channels[chanid]['icon'] = icon
                        self.all_channels[chanid]['icongrp'] = 8
                        self.chan_names[name] = chanid

                for item in htmldata.findall('div/div[@class]/div[@class="grid__col__inner"]/ul/li/a[@href]'):
                    url = item.get('href', '')
                    if url != '':
                        chanid = url.split('/')[-2]
                        if chanid in self.all_channels or chanid == 'bbc1':
                            continue

                        name = self.functions.empersant(item.text).strip()
                        icon = ''

                        self.all_channels[chanid] = {}
                        self.all_channels[chanid]['name'] = name
                        self.chan_names[name] = chanid

        except:
            self.fail_count += 1
            self.config.log( traceback.format_exc())

        changroup = 99
        try:
            if not isinstance(chandata, (str, unicode)):
                chandata = self.config.fetch_func.get_page(self.get_url('base'))

            if chandata == None:
                return 69  # EX_UNAVAILABLE

            strdata = self.getchannelgroups.search(chandata).group(1)
            strdata = re.sub('<img (.*?)"\s*>', '<img \g<1>"/>', strdata)
            strdata = self.functions.clean_html('<div><div>' + strdata).encode('utf-8')
            htmldata = ET.fromstring(strdata)
            for item in htmldata.findall('div/div[@class]'):
                if item.get('class') == 'accordion__header':
                    group =  self.functions.empersant(item.text).strip()
                    if group in chan_groups:
                        changroup = chan_groups[group]

                    else:
                        changroup = 99

                elif item.get('class') == 'accordion__content':
                    for g in item.findall('a[@href]'):
                        pagegrp = g.get('href').split('/')[-1]
                        self.page_strings[pagegrp] = []
                        for c in g.findall('div/img'):
                            cname = c.get('title').strip()
                            icon = c.get('src', '')
                            if icon != '':
                                icon = re.split('/', icon)[-1]
                                chanid = re.split('\.', icon)[0]
                                if (changroup == 99 and chanid in ('npo1', 'npo2', 'npo3')) or chanid in ('tv5', 'bbc1'):
                                    continue

                            if not chanid in self.all_channels.keys():
                                if cname in self.chan_names.keys():
                                    chanid = self.chan_names[cname]

                                elif chanid != '':
                                    self.all_channels[chanid] = {}

                                else:
                                    continue

                            if not 'name' in self.all_channels[chanid] or self.all_channels[chanid]['name'] == '':
                                self.all_channels[chanid]['name'] = cname

                            if not 'icon' in self.all_channels[chanid] or self.all_channels[chanid]['icon'] == '':
                                self.all_channels[chanid]['icon'] = icon
                                self.all_channels[chanid]['icongrp'] = 8

                            self.all_channels[chanid]['pagegrp'] = pagegrp
                            self.page_strings[pagegrp].append(chanid)
                            self.all_channels[chanid]['group'] = changroup

        except:
            self.fail_count += 1
            self.config.log(traceback.format_exc())


    def load_pages(self):
        if self.config.opt_dict['offset'] > 6:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0:
            return

        dayoffset = {}
        dayoffset['vandaag'] = 0
        dayoffset['morgen'] = 1
        dayoffset['overmorgen'] = 2
        for d in range(6):
            dd = self.config.weekdagen[int(datetime.date.fromordinal(self.current_date + d).strftime("%w"))]
            dayoffset[dd] = d

        try:
            for retry in (0, 1):
                channel_cnt = 0
                for chanid in self.channels.keys():
                    channel_cnt += 1
                    failure_count = 0
                    if self.quit:
                        return

                    if self.config.channels[chanid].source_data[self.proc_id].is_set():
                        continue

                    channel = self.channels[chanid]
                    # Nieuwsblad.be either returns 6 days per channel or 3 channels per day for 7 days including today
                    start = self.config.opt_dict['offset']
                    # Check if it is allready loaded
                    if self.day_loaded[chanid][start] != False:
                        continue

                    self.config.log(['\n', 'Now fetching %s(xmltvid=%s%s) from nieuwsblad.be\n' % \
                        (self.config.channels[chanid].chan_name, self.config.channels[chanid].xmltvid , \
                        (self.config.channels[chanid].opt_dict['compat'] and '.tvgids.nl' or '')), \
                        '    (channel %s of %s) for 6 days.\n' % \
                        (channel_cnt, len(self.channels))], 2)

                    # get the raw programming for the day
                    try:
                        channel_url = self.get_url(channel, start)
                        strdata = self.config.fetch_func.get_page(channel_url)

                        if strdata == None:
                            self.config.log("Skip channel=%s on nieuwsblad.be. No data!\n" % (self.config.channels[chanid].chan_name))
                            failure_count += 1
                            self.fail_count += 1
                            continue

                        if self.all_channels == {}:
                            self.get_channel_lineup(strdata)

                    except:
                        self.config.log('Error: "%s" reading the nieuwsblad.be basepage for channel=%s.\n' % \
                            (sys.exc_info()[1], self.config.channels[chanid].chan_name))
                        failure_count += 1
                        self.fail_count += 1
                        continue

                    try:
                        strdata =self.getprograms.search(strdata).group(1)
                        strdata = re.sub('<img (.*?)"\s*>', '<img \g<1>"/>', strdata)
                        strdata = self.functions.clean_html(strdata)
                        htmldata = ET.fromstring(strdata.encode('utf-8'))

                    except:
                        self.config.log(["Error extracting ElementTree for channel:%s on nieuwsblad.be\n" % \
                            (self.config.channels[chanid].chan_name)])

                        if self.config.write_info_files:
                            self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                            self.config.infofiles.write_raw_string(strdata)

                        failure_count += 1
                        self.fail_count += 1
                        self.day_loaded[chanid][offset] = None
                        continue

                    for d in htmldata.findall('div[@class="grid channel-block"]/div[@class="grid__col size-1-3--bp4"]'):
                        weekday = d.findtext('div/div[@class="tv-guide__channel"]/h6/a').strip()
                        offset = dayoffset[weekday]
                        if offset >= self.config.opt_dict['offset'] + self.config.opt_dict['days']:
                            break

                        date_offset = offset
                        scan_date = datetime.date.fromordinal(self.current_date + date_offset)
                        last_program = datetime.datetime.combine(datetime.date.fromordinal(self.current_date + date_offset - 1), \
                                                                                                datetime.time(0, 0, 0 ,0 ,CET_CEST))
                        for p in d.findall('div/div[@class="program"]'):
                            #~ start = p.findtext('div[@class="time"]')
                            #~ title = p.findtext('div[@class="title"]/a').strip()
                            #~ url = p.find('div[@class="title"]/a').get('href')

                            tdict = self.functions.checkout_program_dict()
                            tdict['source'] = u'nieuwsblad'
                            tdict['channelid'] = chanid
                            tdict['channel'] = self.config.channels[chanid].chan_name
                            tdict['detail_url'][self.proc_id] = p.find('div[@class="title"]/a').get('href')
                            #~ tdict['prog_ID'][self.proc_id] = u'tv-%s' % tdict['detail_url'][self.proc_id].split('/')[5]  if (tdict['detail_url'][self.proc_id] != '') else ''

                            # The Title
                            tdict['name'] = self.functions.empersant(p.findtext('div[@class="title"]/a').strip())
                            if  tdict['name'] == None or tdict['name'] == '':
                                self.config.log('Can not determine program title for "%s"\n' % tdict['detail_url'][self.proc_id])
                                continue

                            # Get the starttime and make sure the midnight date change is properly crossed
                            start = p.findtext('div[@class="time"]')
                            if start == None or start == '':
                                self.config.log('Can not determine starttime for "%s"\n' % tdict['name'])
                                continue

                            prog_time = datetime.time(int(start.split(':')[0]), int(start.split(':')[1]), 0 ,0 ,CET_CEST)
                            if datetime.datetime.combine(scan_date, prog_time) < last_program:
                                date_offset = date_offset +1
                                scan_date = datetime.date.fromordinal(self.current_date + date_offset)

                            tdict['offset'] = date_offset
                            tdict['start-time'] = datetime.datetime.combine(scan_date, prog_time)
                            last_program = tdict['start-time']

                            # and append the program to the list of programs
                            tdict = self.check_title_name(tdict)
                            with self.source_lock:
                                self.program_data[chanid].append(tdict)

                        self.base_count += 1
                        self.day_loaded[chanid][offset] = True
                        # be nice to nieuwsblad.be
                        time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))

                    if len(self.program_data[chanid]) == 0:
                        self.config.channels[chanid].source_data[self.proc_id].set()
                        continue

                    # Add starttime of the next program as the endtime
                    with self.source_lock:
                        self.program_data[chanid].sort(key=lambda program: (program['start-time']))
                        self.add_endtimes(chanid, 6)

                        for tdict in self.program_data[chanid]:
                            self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

                    if failure_count == 0 or retry == 1:
                        self.channel_loaded[chanid] = True
                        self.parse_programs(chanid, 0, 'None')
                        self.config.channels[chanid].source_data[self.proc_id].set()

                        try:
                            self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                        except:
                            pass

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread\n' %  (self.source), traceback.format_exc()], 0)
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

# end nieuwsblad_HTML

class primo_HTML(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested channels
    from the primo.eu page. Based on FetchData Class
    """
    def init_channels(self):

        # These regexes fetch the relevant data out of the nieuwsblad.be pages, which then will be parsed to the ElementTree
        self.getmain = re.compile('<!--- HEADER SECTION -->(.*?)<!-- USER PROFILE-->',re.DOTALL)
        self.getchannelstring = re.compile('(.*?) channel channel-(.*?) channel-.*?')
        self.getprogduur = re.compile('width:(\d+)px;')

        self.init_channel_source_ids()
        self.chanids = {}
        for chanid, sourceid in self.channels.items():
            self.chanids[sourceid] = chanid

    def get_url(self, offset = 0, detail = None):
        base_url = 'http://www.primo.eu'
        if offset == 'channels':
            return base_url + "/Tv%20programma's%20in%20volledig%20scherm%20bekijken"

        elif detail == None and isinstance(offset, int):
            date = self.functions.get_datestamp(offset)
            return '%s/tv-programs-full-view/%s/all/all' % (base_url, date)

        else:
            return u'%s/tvprograms/ajaxcallback/%s' % (base_url,  detail)

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        try:
            strdata = self.config.fetch_func.get_page(self.get_url('channels'))
            if self.get_channel_lineup(strdata) == 69:
                self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
                return 69  # EX_UNAVAILABLE

        except:
            self.fail_count += 1
            self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
            return 69  # EX_UNAVAILABLE

    def get_channel_lineup(self, chandata):

        try:
            if not isinstance(chandata, (str, unicode)):
                chandata = self.config.fetch_func.get_page(self.get_url(0))

            strdata = self.getmain.search(chandata).group(1)
            strdata = self.functions.clean_html(strdata).encode('utf-8')
            htmldata = ET.fromstring(strdata)
            htmldata = htmldata.find('div/div[@id="tvprograms-main"]/div[@id="tvprograms"]')
            for item in htmldata.findall('div[@id="program-channel-programs"]/div/div/div'):
                if item.get("style") != None:
                    continue

                chan_string = self.getchannelstring.search(item.get("class"))
                chanid = chan_string.group(1)
                cname = chan_string.group(2)
                icon_search = 'div[@id="program-channels-list-main"]/div/ul/li/div/a/img[@class="%s"]' % chanid
                icon = htmldata.find(icon_search)
                if icon == None:
                    icon = ''

                else:
                    icon = re.split('/',icon.get("src"))[-1]

                if not chanid in self.all_channels.keys():
                    self.all_channels[chanid] = {}
                    self.all_channels[chanid]['name'] = cname
                    self.all_channels[chanid]['icon'] = icon
                    self.all_channels[chanid]['icongrp'] = 9

        except:
            self.fail_count += 1
            self.config.log(traceback.format_exc())
            return 69

    def load_pages(self):
        if self.config.opt_dict['offset'] > 7:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0:
            return

        try:
            for retry in (0, 1):
                for offset in range( self.config.opt_dict['offset'], min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 7)):
                    failure_count = 0
                    if self.quit:
                        return

                    # Check if it is allready loaded
                    if self.day_loaded[0][offset] != False:
                        continue

                    self.config.log(['\n', 'Now fetching channels from primo.eu for day %s of %s\n' % \
                        (offset, self.config.opt_dict['days'])], 2)

                    # get the raw programming for the day
                    try:
                        channel_url = self.get_url(offset)
                        strdata = self.config.fetch_func.get_page(channel_url)

                        if strdata == None:
                            self.config.log("Skip day=%s on primo.eu. No data!\n" % (offset))
                            failure_count += 1
                            self.fail_count += 1
                            continue

                        if self.all_channels == {}:
                            self.get_channel_lineup(strdata)

                    except:
                        self.config.log('Error: "%s" reading the primo.eu basepage for day %s.\n' % \
                            (sys.exc_info()[1], offset))
                        failure_count += 1
                        self.fail_count += 1
                        continue

                    try:
                        strdata =self.getmain.search(strdata).group(1)
                        strdata = self.functions.clean_html(strdata)
                        htmldata = ET.fromstring(strdata.encode('utf-8'))
                        htmldata = htmldata.find('div/div[@id="tvprograms-main"]/div[@id="tvprograms"]')
                        sel_date = htmldata.findtext('div[@id="program-header-top"]/div/div[@id="dates"]/ul/li[@class="selected-date"]/a/span[@class="day"]')
                        if sel_date in ('', None) or datetime.date.fromordinal(self.current_date + offset).day != int(sel_date):
                            self.config.log("Skip day=%d on Primo.eu. Wrong date: %s(timestamp: %s!\n" % (offset, sel_date, self.functions.get_datestamp(offset)))
                            failure_count += 1
                            self.fail_count += 1
                            continue


                    except:
                        self.config.log(["Error extracting ElementTree for day:%s on primo.eu\n" % (offset)])

                        if self.config.write_info_files:
                            self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                            self.config.infofiles.write_raw_string(strdata)

                        failure_count += 1
                        self.fail_count += 1
                        continue

                    for chan in htmldata.findall('div[@id="program-channel-programs"]/div/div/div'):
                        if chan.get("style") != None:
                            continue

                        scid = self.getchannelstring.search(chan.get("class")).group(1)
                        if not scid in self.chanids.keys():
                            continue

                        chanid = self.chanids[scid]
                        date_offset = offset -1
                        last_end = datetime.datetime.combine(datetime.date.fromordinal(self.current_date + offset), \
                                                                                        datetime.time(hour=6, tzinfo=CET_CEST))
                        for d in chan.findall('div[@class="hour hour-"]'):
                            date_offset+=1
                            scan_date = datetime.date.fromordinal(self.current_date + date_offset)
                            for p in d.findall('div'):
                                tdict = self.functions.checkout_program_dict()
                                tdict['source'] = u'primo'
                                tdict['channelid'] = chanid
                                tdict['channel'] = self.config.channels[chanid].chan_name
                                pid = p.find('h3').get('id')
                                tdict['prog_ID'][self.proc_id] = u'primo-%s' % pid  if pid != None else ''
                                tdict['detail_url'][self.proc_id] = self.get_url(detail = pid)  if pid != None else ''

                                # The Title
                                tdict['name'] = self.functions.empersant(p.findtext('h3').strip())
                                if  tdict['name'] == None or tdict['name'] == '':
                                    self.config.log('Can not determine program title for "%s"\n' % tdict['detail_url'][self.proc_id])
                                    continue

                                # Get the starttime and make sure the midnight date change is properly crossed
                                ptime = p.findtext('span', '')
                                pduur = int(self.getprogduur.search(p.get('style')).group(1))*12
                                if ptime == '':
                                    tdict['start-time'] = last_end
                                    tdict['stop-time'] = last_end + datetime.timedelta(seconds=pduur)

                                else:
                                    ptime = ptime.split('-')
                                    pstart = ptime[0].strip().split('.')
                                    prog_time = datetime.time(hour=int(pstart[0]), minute=int(pstart[1]), tzinfo=CET_CEST)
                                    tdict['offset'] = date_offset
                                    tdict['start-time'] = datetime.datetime.combine(scan_date, prog_time)
                                    pstop = ptime[1].strip().split('.')
                                    prog_time = datetime.time(hour=int(pstop[0]), minute=int(pstop[1]), tzinfo=CET_CEST)
                                    tdict['offset'] = date_offset
                                    tdict['stop-time'] = datetime.datetime.combine(scan_date, prog_time)
                                    if tdict['stop-time'] < tdict['start-time']:
                                        tdict['stop-time'] = datetime.datetime.combine(datetime.date.fromordinal(self.current_date + date_offset + 1), prog_time)

                                last_end = tdict['stop-time']

                                # and append the program to the list of programs
                                tdict = self.check_title_name(tdict)
                                with self.source_lock:
                                    self.program_data[chanid].append(tdict)

                    self.base_count += 1
                    self.day_loaded[0][offset] = True
                    # be nice to nieuwsblad.be
                    time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))

                if failure_count == 0 or retry == 1:
                    for chanid in self.channels.keys():
                        self.program_data[chanid].sort(key=lambda program: (program['start-time'],program['stop-time']))
                        self.parse_programs(chanid, 0, 'None')
                        self.channel_loaded[chanid] = True
                        self.config.channels[chanid].source_data[self.proc_id].set()
                        with self.source_lock:
                            for tdict in self.program_data[chanid]:
                                self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

                        try:
                            self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                        except:
                            pass

                    return

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread\n' %  (self.source), traceback.format_exc()], 0)
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

    def load_detailpage(self, tdict):
        try:
            strdata = self.config.fetch_func.get_page(tdict['detail_url'][self.proc_id], 'utf-8')
            if strdata == None:
                return

            strdata = self.functions.clean_html('<root>' + strdata + '</root>').encode('utf-8')
        except:
            self.config.log(['Error Fetching detailpage %s\n' % tdict['detail_url'][self.proc_id], traceback.format_exc()])
            return None

        try:
            htmldata = ET.fromstring(strdata)

        except:
            self.config.log("Error extracting ElementTree from:%s on primo.eu\n" % (tdict['detail_url'][self.proc_id]))
            if self.config.write_info_files:
                self.config.infofiles.write_raw_string('Error: %s at line %s\n\n' % (sys.exc_info()[1], sys.exc_info()[2].tb_lineno))
                self.config.infofiles.write_raw_string(strdata + u'\n')

            return None

        try:
            genre = ''
            subgenre = ''
            for d in htmldata.findall('div/div[@class="details"]/div'):
                dlabel = d.findtext('label')[:-1].lower().strip()
                ddata = self.functions.empersant(d.findtext('span')).strip()
                if ddata in (None, '-'):
                    ddata = ''

                try:
                    if dlabel in ("programmanaam", "datum en tijd", "zender"):
                        continue

                    elif dlabel == "synopsis":
                        tdict['description'] = ddata

                    elif dlabel == "titel aflevering":
                        tdict['titel aflevering'] = ddata if ((ddata != tdict['name'])) else ''
                        tdict = self.check_title_name(tdict)

                    elif dlabel == "nr. aflevering":
                        tdict['episode'] = 0 if (ddata  == '') else int(ddata)

                    elif dlabel == "seizoen":
                        tdict['season'] = 0 if (ddata == '') else int(ddata)


                    elif dlabel in  self.config.roletrans.keys():
                        if not self.config.roletrans[dlabel] in tdict['credits']:
                            tdict['credits'][config.roletrans[dlabel]] = []

                        for p in d.findall('span'):
                            name = self.functions.empersant(p.text).split('(')[0].strip()
                            if not name in tdict['credits'][config.roletrans[dlabel]]:
                                tdict['credits'][config.roletrans[dlabel]].append(name)

                    elif dlabel == "jaar":
                        tdict['jaar van premiere'] = ddata

                    elif dlabel == "land":
                        #~ tdict['country']
                        ddata = re.sub('.', '', ddata).upper()
                        ddata = re.split(',', ddata)
                        for c in ddata:
                            if c in self.config.coutrytrans.values():
                                tdict['country'] = cstr
                                break

                            elif c in self.config.coutrytrans.keys():
                                tdict['country'] = self.config.coutrytrans[cstr]
                                break

                            elif self.config.write_info_files:
                                self.config.infofiles.addto_detail_list(u'new country => %s' % (c))

                    elif dlabel == "genre":
                        genre = ddata if len(ddata) > 2 else ''

                    elif dlabel == "samenvatting":
                        subgenre = ddata if len(ddata) <= 25 else ''

                    #~ elif dlabel == "rating":
                        #~ pass

                    #~ elif dlabel == "minimumleeftijd":
                        #~ pass

                    #~ elif dlabel == "":
                        #~ pass

                    elif self.config.write_info_files:
                        self.config.infofiles.addto_detail_list(u'new primo-tag => %s: %s' % (dlabel, ddata))

                except:
                    continue

            if (genre, subgenre) in self.config.source_cattrans[self.proc_id].keys():
                tdict['genre'] = self.config.source_cattrans[self.proc_id][(genre, subgenre)][0]
                if self.config.source_cattrans[self.proc_id][(genre, subgenre)][1] == '':
                    tdict['subgenre'] = subgenre

                else:
                    tdict['subgenre'] = self.config.source_cattrans[self.proc_id][(genre, subgenre)][1]

            elif genre in self.config.source_cattrans[self.proc_id].keys():
                tdict['genre'] = self.config.source_cattrans[self.proc_id][genre][0]
                if self.config.source_cattrans[self.proc_id][genre][1] == '':
                    tdict['subgenre'] = subgenre
                    if subgenre != '':
                        self.config.new_cattrans[self.proc_id][(genre, subgenre)] = (self.config.source_cattrans[self.proc_id][genre][0], subgenre)

                else:
                    tdict['subgenre'] = self.config.source_cattrans[self.proc_id][genre][1]

                if self.config.write_info_files and subgenre != '':
                    self.config.infofiles.addto_detail_list(u'new primo-subgenre => %s: %s' % (genre, subgenre))

            elif genre != '':
                tdict['genre'] = genre
                tdict['subgenre'] = subgenre
                self.config.new_cattrans[self.proc_id][(genre, subgenre)] = (genre, subgenre)
                if self.config.write_info_files and subgenre != '':
                    self.config.infofiles.addto_detail_list(u'new primo-genre => %s: %s' % (genre, subgenre))

            else:
                tdict['genre'] = 'overige'
                tdict['subgenre'] = ''

        except:
            self.config.log(['Error processing Primo.eu detailpage:%s\n' % (tdict['detail_url'][self.proc_id]), traceback.format_exc()])
            return

        tdict['ID'] = tdict['prog_ID'][self.proc_id]
        tdict[self.detail_check] = True

        return tdict

# end primo_HTML

class vrt_JSON(tv_grab_fetch.FetchData):
    def init_channels(self):
        self.init_channel_source_ids()
        self.chanids = {}
        for chanid, sourceid in self.channels.items():
            self.chanids[sourceid] = chanid

    def get_url(self, type = 'channels', offset = 0, chanid = None):

        base_url = 'http://services.vrt.be/'
        scan_date = datetime.date.fromordinal(self.current_date + offset).strftime('%Y%m%d')

        if type == 'channels':
            return  [u'%schannel/s' % (base_url), 'application/vnd.channel.vrt.be.channels_1.1+json']

        elif type == 'genres':
            return  [u'%sepg/standardgenres' % (base_url), 'application/vnd.epg.vrt.be.standardgenres_1.0+json']

        elif type == 'week' and chanid == None:
            return  [u'%sepg/schedules/%s?type=week' % (base_url, scan_date),
                            'application/vnd.epg.vrt.be.schedule_3.1+json']

        elif type == 'week':
            return  [u'%sepg/schedules/%s?type=week&channel_code=%s' % (base_url, scan_date, chanid),
                            'application/vnd.epg.vrt.be.schedule_3.1+json']

        elif type == 'day' and chanid == None:
            return  [u'%sepg/schedules/%s?type=day' % (base_url, scan_date),
                            'application/vnd.epg.vrt.be.schedule_3.1+json']

        elif type == 'day':
            return  [u'%sepg/schedules/%s?type=day&channel_code=%s' % (base_url, scan_date, chanid),
                            'application/vnd.epg.vrt.be.schedule_3.1+json']

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        # download the json feed
        url = self.get_url()
        total = self.config.fetch_func.get_page(url[0], 'utf-8', url[1])
        if total == None:
            self.config.log("Unable to get channel info from %s\n" % self.source)
            return 69  # EX_UNAVAILABLE

        channel_list = json.loads(total)

        # and create a file with the channels
        self.all_channels ={}
        for channel in channel_list['channels']:
            if channel['state'] == 'inactive':
                continue

            chanid = channel['code']
            self.all_channels[chanid] = {}
            self.all_channels[chanid]['name'] = self.functions.unescape(channel['displayName']).strip()
            if channel['type'] == 'tv':
                self.all_channels[chanid]['group'] = 2

            elif channel['type'] == 'radio':
                self.all_channels[chanid]['group'] = 12

            else:
                self.all_channels[chanid]['group'] = 99

            icon = channel['logoUrl'].split('/')
            if icon[2] == 'images.vrt.be':
                self.all_channels[chanid]['icon'] =  '%s/%s' % (icon[-2] , icon[-1])
                self.all_channels[chanid]['icongrp'] = 11

            if icon[2] == 'services.vrt.be':
                self.all_channels[chanid]['icon'] = icon[-1]
                self.all_channels[chanid]['icongrp'] = 10

    def get_datetime(self, date_string, round_down = True):
        date = datetime.datetime.strptime(date_string.split('.')[0], '%Y-%m-%dT%H:%M:%S').replace(tzinfo = UTC).astimezone(CET_CEST)
        seconds = date.second
        date = date.replace(second = 0)
        if seconds > 0 and not round_down:
            date = date + datetime.timedelta(minutes = 1)

        return date

    def get_standaardgenres(self):
        url = self.get_url('genres')
        total = self.config.fetch_func.get_page(url[0], 'utf-8', url[1])
        genredict = json.loads(total)
        vrt_genres = {}
        dvb_genres = {}
        ebu_genres = {}
        for g in genredict['standardGenres']:
            vrt_genres[g['code']] = {}
            vrt_genres[g['code']]['type'] = [g['type']]
            vrt_genres[g['code']]['eid'] = [g['eid']]
            vrt_genres[g['code']]['type'] = [g['type']]
            vrt_genres[g['code']]['name'] = [g['name']]
            eid = g['eid'].split('.')
            name =  g['name'].split('>')
            if g['type'] == 'DVB':
                if eid[1] == '0':
                    #~ eid[1] = ''
                    eid.pop(1)
                    name[1] = ''

                dvb_genres[tuple(eid)] = tuple(name)

            elif g['type'] == 'EBU':
                pass

        gkeys = dvb_genres.keys()
        for k in sorted(dvb_genres.keys()):
            print(u'%s: %s,' % (k, dvb_genres[k]))

    def load_pages(self):
        radio_channels = ('13','12','03','31','32','41','55','56','11','21','22','23','24','25')
        if self.config.opt_dict['offset'] > 14:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0 :
            return

        first_fetch = True
        groupitems = {}
        week_loaded = {}
        fetch_dates = []
        first_day = int(datetime.date.fromordinal(self.current_date + self.config.opt_dict['offset']).strftime('%w'))
        first_day = self.config.opt_dict['offset'] + 1 - first_day if first_day > 0 else self.config.opt_dict['offset'] - 6
        fetch_range = range(first_day, (self.config.opt_dict['offset'] + self.config.opt_dict['days']), 7)
        for d in range(self.config.opt_dict['offset'], (self.config.opt_dict['offset'] + self.config.opt_dict['days'])):
            fetch_dates.append(datetime.date.fromordinal(self.current_date + d).strftime('%Y-%m-%d'))

        for chanid in self.channels.keys():
            groupitems[chanid] = 0
            week_loaded[chanid] = {}
            for r in range(len(fetch_range)):
                week_loaded[chanid][r] = False

        try:
            for retry in (0, 1):
                channel_cnt = 0
                for chanid, channel in self.channels.items():
                    channel_cnt += 1
                    failure_count = 0
                    if self.quit:
                        return

                    for offset in range(len(fetch_range)):
                        if self.quit:
                            return

                        # Check if it is already loaded
                        if week_loaded[chanid][offset]:
                            continue

                        url = self.get_url('week', fetch_range[offset], channel)
                        self.config.log(['\n', 'Now fetching %s(xmltvid=%s%s) from vrt.be\n' % \
                            (self.config.channels[chanid].chan_name, self.config.channels[chanid].xmltvid , \
                            (self.config.channels[chanid].opt_dict['compat'] and '.tvgids.nl' or '')), \
                            '    (channel %s of %s) for week %s of %s).\n' % \
                            (channel_cnt, len(self.channels), offset, len(fetch_range))], 2)

                        # be nice to vrt.be
                        if not first_fetch:
                            time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))
                            first_fetch = False

                        # get the raw programming for the day
                        try:
                            strdata = self.config.fetch_func.get_page(url[0], 'utf-8', url[1])

                            if strdata == None:
                                self.config.log("No data on vrt.be for %s, week=%d!\n" % (self.config.channels[chanid].chan_name, offset))
                                failure_count += 1
                                self.fail_count += 1
                                continue

                        except:
                            self.config.log('Error: "%s" reading the vrt.be json page for %s, week=%d.\n' % \
                                (sys.exc_info()[1], self.config.channels[chanid].chan_name, offset))
                            failure_count += 1
                            self.fail_count += 1
                            continue

                        self.base_count += 1
                        week_loaded[chanid][offset] = True
                        jsondata = json.loads(strdata)
                        for p in jsondata['events']:
                            if not (p['date'] in fetch_dates and p['channel']['code'] in self.channels.values()):
                                continue

                            tdict = self.functions.checkout_program_dict()
                            tdict['prog_ID'][self.proc_id] = u'vrt-%s' % (p['code'])
                            self.json_by_id[tdict['prog_ID'][self.proc_id]] = p
                            tdict['source'] = 'vrt'
                            tdict['channelid'] = chanid
                            tdict['channel']  = self.config.channels[chanid].chan_name

                            # The Title
                            tdict['name'] = self.functions.unescape(p['title'])

                            # The timing
                            tdict['start-time'] = self.get_datetime(p['startTime'])
                            tdict['stop-time']  = self.get_datetime(p['endTime'], False)
                            if  tdict['name'] == None or tdict['name'] == '' or tdict['start-time'] == None or tdict['stop-time'] == None:
                                continue

                            tdict['offset'] = self.functions.get_offset(tdict['start-time'])
                            if 'shortDescription' in p.keys() and p['shortDescription'] not in ('', None):
                                tdict['description'] = p['shortDescription']

                            elif 'description' in p.keys() and p['description'] not in ('', None):
                                tdict['description'] = p['description']

                            if 'group' in p.keys():
                                tdict['group'] = p['group']
                                groupitems[chanid] +=1

                            if 'episodeTitle' in p and p['episodeTitle'] != None:
                                if p['episodeTitle'].lower().strip() != tdict['name'].lower().strip():
                                    tdict['titel aflevering'] = p['episodeTitle'].strip()

                            # Types
                            # Aflevering, Nieuws, Sport, Programma, Film, Groep, Weerbericht, radio, Kansspelen, Volatiel,
                            # MER, Feratel beelden, Volatiel programma - geen PDC, Main Transmission, Dia, NACHTLUS op MER
                            if p['type'] in ('Aflevering', 'Programma'):
                                if 'seasonNumber' in p and p['seasonNumber'] not in ('', None):
                                    try:
                                        tdict['season'] = int(p['seasonNumber'])

                                    except:
                                        pass

                                if 'episodeNumber' in p and p['episodeNumber'] not in ('', None):
                                    try:
                                        tdict['episode'] = int(p['episodeNumber'])

                                    except:
                                        pass

                            if 'presenters' in p and isinstance(p['presenters'], list):
                                if not 'presenter' in tdict['credits']:
                                    tdict['credits']['presenter'] = []

                                for d in p['presenters']:
                                    if 'name' in d:
                                        tdict['credits']['presenter'].append(d['name'])

                            if 'cast' in p and p['cast'] not in ('', None):
                                cast_items = self.get_string_parts(p['cast'])
                                for crole, cast in cast_items.items():
                                    if len(cast) == 0:
                                        continue

                                    elif crole in self.config.roletrans.keys():
                                        role = self.config.roletrans[crole]
                                        if not role in tdict['credits']:
                                            tdict['credits'][role] = []

                                        cast = re.sub('\) ([A-Z])', '), \g<1>', \
                                                re.sub(' en ', ', ', \
                                                re.sub('e\.a\.', '', cast[0]))).split(',')
                                        for cn in cast:
                                            tdict['credits'][role].append(cn.split('(')[0].strip())

                                    elif self.config.write_info_files:
                                        self.config.infofiles.addto_detail_list(u'new vrt cast item => %s = %s' % (crole, cast))

                            # standardGenres
                            # actua, sport, cultuur, film, docu, humor, series, ontspanning
                            if 'standardGenres' in p.keys() and isinstance(p['standardGenres'], dict):
                                if p['standardGenres']['type'] == 'DVB':
                                    pg = p['standardGenres']['eid'].split('.')
                                    pn =  p['standardGenres']['name'].split('>')
                                    if pg in self.config.source_cattrans[self.proc_id].keys():
                                        tdict['genre'] = self.config.source_cattrans[self.proc_id][pg][0].capitalize()
                                        tdict['subgenre'] = self.config.source_cattrans[self.proc_id][pg][1].capitalize()

                                    elif (pg[0].lower(), ) in self.config.source_cattrans[self.proc_id].keys():
                                        tdict['genre'] = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )][0].capitalize()
                                        sg = self.config.source_cattrans[self.proc_id][(pg[0].lower(), )][1]
                                        tdict['subgenre'] = pn[1] if sg == '' else sg.capitalize()
                                        self.config.new_cattrans[self.proc_id][(pg[0], pg[1])] = (tdict['genre'], tdict['subgenre'])

                                    else:
                                        tdict['genre'] = u'overige'
                                        tdict['subgenre'] = pn[1]
                                        self.config.new_cattrans[self.proc_id][pg] = (u'Overige', pn[1])

                            if tdict['genre'] == u'overige' and channel in radio_channels:
                                if 'muziek' in tdict['description'] or 'muziek' in tdict['name']:
                                    tdict['genre'] = u'muziek'

                                elif 'nieuws ' in tdict['description'] or 'nieuws ' in tdict['name']:
                                    tdict['genre'] = u'nieuws/actualiteiten'

                                elif 'sport' in tdict['description'] or 'sport' in tdict['name']:
                                    tdict['genre'] = u'sport'

                                elif 'actualiteiten' in tdict['description'] or 'actualiteiten' in tdict['name']:
                                    tdict['genre'] = u'nieuws/actualiteiten'

                            tdict['video']['breedbeeld'] = True if 'aspectRatio' in p.keys() and p['aspectRatio'] == '16:9' else False
                            tdict['video']['HD'] = True if 'videoFormat' in p.keys() and p['videoFormat'] == 'HD' else False
                            tdict['teletekst'] = True if 'hasTTSubTitles' in p.keys() and p['hasTTSubTitles'] else False
                            tdict['rerun'] = True if 'isRepeat' in p.keys() and p['isRepeat'] else False
                            if 'categories' in p.keys() and p['categories'] != None and p['categories'].strip() != '':
                                if p['categories'].strip() in  self.config.vrtkijkwijzer:
                                    tdict['kijkwijzer'].append(self.config.vrtkijkwijzer[p['categories'].strip()])

                                elif self.config.write_info_files:
                                    self.config.infofiles.addto_detail_list(u'new vrt categorie => %s' % (p['categories']))

                            if self.config.write_info_files:
                                for item in p.keys():
                                    if item.strip() not in (u'code', u'date', u'channel', u'programme', u'group', u'season', u'episode', u'brand',
                                            u'twitterHashTag', u'onDemandURL', u'episodeOnDemandURL', u'websiteURL', u'secondScreenURL',
                                            u'images', u'imagesLink', u'trailerURL', u'trailerPictureURL', u'playlistLink', u'playlistSiteURL',
                                            u'onAir', u'geoblocking', u'isLive', u'hidePrintedPress', u'bought', u'onDemand',
                                            u'updateFlag', u'whatsonProductId', u'reconcileId',u'pdc' ,
                                            u'title', u'shortTitle', u'startTime', u'endTime', u'duration', u'originalStartTime',
                                            u'seasonNumber', u'seasonEid', u'seasonTitle', u'seasonNumberOfEpisodes', u'hideSeasonNumber',
                                            u'episodeNumber', u'episodeEid', u'episodeSequenceNumber', u'episodeTitle', u'hideEpisodeNumber',
                                            u'aspectRatio', u'videoFormat', u'hasTTSubTitles', u'isRepeat',
                                            u'presenters', u'cast', u'type', u'categories', u'standardGenres',
                                            u'shortDescription', u'description', u'hasAudioDescription'):
                                        self.config.infofiles.addto_detail_list(u'new vrt key => %s = %s' % (item, p[item]))

                            tdict = self.check_title_name(tdict)
                            with self.source_lock:
                                self.program_data[chanid].append(tdict)

                    if failure_count == 0 or retry == 1:
                        with self.source_lock:
                            self.program_data[chanid].sort(key=lambda program: (program['start-time'],program['stop-time']))
                            # 1 or more groups were encountered
                            if groupitems[chanid] > 0:
                                group_start = False
                                for p in self.program_data[chanid][:]:
                                    if 'group' in p.keys():
                                        # Collecting the group
                                        if not group_start:
                                            group = []
                                            start = p['start-time']
                                            group_start = True

                                        group.append(p.copy())
                                        group_duur = p['stop-time'] - start

                                    elif group_start:
                                        # Repeating the group
                                        group_start = False
                                        group_eind = p['start-time']
                                        group_length = group_eind - start
                                        if group_length > datetime.timedelta(days = 1):
                                            # Probably a week was not grabbed
                                            group_eind -= datetime.timedelta(days = int(group_length.days))

                                        repeat = 0
                                        while True:
                                            repeat+= 1
                                            for g in group[:]:
                                                gdict = g.copy()
                                                gdict['prog_ID'][self.proc_id] = ''
                                                gdict['rerun'] = True
                                                gdict['start-time'] += repeat*group_duur
                                                gdict['stop-time'] += repeat*group_duur
                                                if gdict['start-time'] < group_eind:
                                                    if gdict['stop-time'] > group_eind:
                                                        gdict['stop-time'] = group_eind

                                                    self.program_data[chanid].append(gdict)

                                                else:
                                                    break

                                            else:
                                                continue

                                            break

                        self.parse_programs(chanid, 0, 'None')
                        self.channel_loaded[chanid] = True
                        for day in range( self.config.opt_dict['offset'], (self.config.opt_dict['offset'] + self.config.opt_dict['days'])):
                            self.day_loaded[chanid][day] = True

                        self.config.channels[chanid].source_data[self.proc_id].set()
                        try:
                            self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                        except:
                            pass

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread:\n' %  (self.source), traceback.format_exc()], 0)

            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()
            return None

# end vrt_JSON

class Virtual_Channels(tv_grab_fetch.FetchData):
    """
    This source is for creating combined channels
    """
    def get_channels(self):
        self.all_channels = self.config.virtual_channellist

# end Virtual_Channels

class oorboekje_HTML(tv_grab_fetch.FetchData):
    """
    Get all available days of programming for the requested radio channels
    from the oorboekje.nl page. Based on FetchData Class
    """
    def init_channels(self):

        self.gettable = re.compile('<TABLE (.*?)</TABLE>',re.DOTALL)
        self.gettablerow = re.compile('<TD valign(.*?)</TD>',re.DOTALL)
        self.getregional = re.compile("Regionale .*? zenders:")
        self.getchanid = re.compile('A href="stream.php\?zender=([0-9]+)"')
        self.getchanname = re.compile('<P class="pnZender".*?>(.*?)</P>',re.DOTALL)
        self.getnameaddition = re.compile('<SPAN style=".*?">(.*?)</SPAN>')
        self.getdate = re.compile("this.document.title='oorboekje.nl - Programma-overzicht van .*? ([0-9]{2})-([0-9]{2})-([0-9]{4})';")
        self.getchanday = re.compile('<!-- programmablok begin -->(.*?)<!-- programmablok eind -->',re.DOTALL)
        self.getchannel = re.compile('<A href="zenderInfo.php\?zender=([0-9]+).*?</A>(.*?)</DIV>',re.DOTALL)
        self.getprogram = re.compile('<DIV class="pgProgOmschr" style="text-indent: -16px; padding-left: 16px">\s*([0-9]{2}):([0-9]{2})\s*(.*?)<B>(.*?)</B>(.*?)</DIV>',re.DOTALL)
        self.gettime = re.compile('([0-9]{2}):([0-9]{2})')
        self.geticons = re.compile('<IMG src=".*?" alt="(.*?)".*?>',re.DOTALL)
        self.init_channel_source_ids()
        self.chanids = {}
        for chanid, sourceid in self.channels.items():
            self.chanids[sourceid] = chanid

    def get_url(self, type = None, offset = 0):

        base_url = 'http://www.oorboekje.nl/'
        week_day = datetime.date.fromordinal(self.current_date + offset).isoweekday()

        if type == 'channels':
            return  base_url

        else:
            return u'%sprogram.php?dag=%s' % (base_url, week_day)

    def get_channels(self):
        """
        Get a list of all available channels and store these
        in all_channels.
        """

        try:
            strdata = self.config.fetch_func.get_page(self.get_url('channels'))
            if self.get_channel_lineup(strdata) == 69:
                self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
                return 69  # EX_UNAVAILABLE

        except:
            self.fail_count += 1
            self.config.log(["Unable to get channel info from %s\n" % self.source, traceback.format_exc()])
            return 69  # EX_UNAVAILABLE

    def get_channel_lineup(self, chandata):

        try:
            if not isinstance(chandata, (str, unicode)):
                return 69

            strdata = self.gettable.search(chandata).group(0)
            strdata = self.functions.clean_html(strdata)
            chgroup = 11
            for ch in self.gettablerow.findall(strdata):
                if not '"stream.php?zender=' in ch:
                    if self.getregional.search(ch) != None:
                        chgroup = 17

                    continue

                chanid = self.getchanid.search(ch).group(1)
                channame = self.getchanname.search(ch).group(1)
                regionname = self.getnameaddition.search(channame)
                channame = self.functions.empersant(re.sub('<SPAN.*?</SPAN>', '', channame).strip())
                if regionname != None and not '(' in regionname.group(1):
                    channame = u'%s %s' % (channame, regionname.group(1))

                if not chanid in self.all_channels.keys():
                    self.all_channels[chanid] = {}
                    self.all_channels[chanid]['name'] = channame
                    self.all_channels[chanid]['group'] = chgroup

                #~ print chgroup, chanid, channame.encode('utf-8')
                #~ print '			"12-%s": "%s",' % (chanid, chanid)

        except:
            self.fail_count += 1
            self.config.log(traceback.format_exc())
            return 69

    def load_pages(self):
        if self.config.opt_dict['offset'] > 7:
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

            return

        if len(self.channels) == 0:
            return

        try:
            for retry in (0, 1):
                failure_count = 0
                for offset in range( self.config.opt_dict['offset'], min((self.config.opt_dict['offset'] + self.config.opt_dict['days']), 7)):
                    if self.quit:
                        return

                    # Check if it is allready loaded
                    if self.day_loaded[0][offset] != False:
                        continue

                    self.config.log(['\n', 'Now fetching channels from oorboekje.nl for day %s of %s\n' % \
                        (offset, self.config.opt_dict['days'])], 2)

                    # get the raw programming for the day
                    try:
                        channel_url = self.get_url(offset=offset)
                        strdata = self.config.fetch_func.get_page(channel_url)

                        if strdata == None:
                            self.config.log("Skip day=%s on oorboekje.nl. No data!\n" % (offset))
                            failure_count += 1
                            self.fail_count += 1
                            continue

                        fetchdate = self.getdate.search(strdata)
                        if fetchdate == None or datetime.date.fromordinal(self.current_date + offset) != \
                          datetime.date(int(fetchdate.group(3)), int(fetchdate.group(2)), int(fetchdate.group(1))):
                            self.config.log('Invalid date for oorboekje.nl for day %s.\n' % offset)

                    except:
                        self.config.log('Error: "%s" reading the oorboekje.nl basepage for day %s.\n' % \
                            (sys.exc_info()[1], offset))
                        failure_count += 1
                        self.fail_count += 1
                        continue

                    strdata = self.functions.clean_html(strdata)
                    for ch in self.getchanday.findall(strdata):
                        chan = self.getchannel.search(ch)
                        if chan == None:
                            continue

                        scid = chan.group(1)
                        channame = self.functions.empersant(re.sub('<SPAN.*?</SPAN>', '', chan.group(2)).strip())
                        if not scid in self.all_channels:
                             self.all_channels[scid] ={}

                        self.all_channels[scid]['name'] = channame
                        if not scid in self.chanids.keys():
                            continue

                        chanid = self.chanids[scid]
                        date_offset = offset
                        last_end = datetime.datetime.combine(datetime.date.fromordinal(self.current_date + offset),
                                                                                        datetime.time(hour=0, tzinfo=CET_CEST))
                        scan_date = datetime.date.fromordinal(self.current_date + date_offset)
                        pcount = 0
                        for p in self.getprogram.findall(ch):
                            tdict = self.functions.checkout_program_dict()
                            tdict['source'] = u'oorboekje'
                            tdict['channelid'] = chanid
                            tdict['channel'] = self.config.channels[chanid].chan_name

                            # The Title
                            tdict['name'] = self.functions.empersant(p[3].strip())
                            if  tdict['name'] == None or tdict['name'] == '':
                                self.config.log('Can not determine program title\n')
                                continue

                            pcount+=1
                            ptime = datetime.time(int(p[0]), int(p[1]), tzinfo=CET_CEST)
                            tdict['offset'] = date_offset
                            tdict['start-time'] = datetime.datetime.combine(scan_date, ptime)
                            if tdict['start-time'] < last_end:
                                if pcount > 2:
                                    scan_date = datetime.date.fromordinal(self.current_date + date_offset+1)
                                    tdict['start-time'] = datetime.datetime.combine(scan_date, ptime)

                            last_end = tdict['start-time']
                            ptime = self.gettime.search(p[2])
                            if ptime != None:
                                ptime = datetime.time(int(ptime.group(1)), int(ptime.group(2)), tzinfo=CET_CEST)
                                tdict['stop-time'] = datetime.datetime.combine(scan_date, ptime)
                                if tdict['stop-time'] < last_end:
                                    scan_date = datetime.date.fromordinal(self.current_date + date_offset+1)
                                    tdict['stop-time'] = datetime.datetime.combine(scan_date, ptime)

                                last_end = tdict['stop-time']

                            for picon in self.geticons.findall(p[4]):
                                if picon == "herhaling":
                                    tdict['rerun'] = True

                                elif picon == "nonstop":
                                    tdict['genre'] = u'muziek'

                            desc = re.sub('<.*?>', '', self.functions.empersant(p[4])).strip()
                            if tdict['genre'] == u'overige':
                                if 'muziek' in desc or 'muziek' in tdict['name']:
                                    tdict['genre'] = u'muziek'

                                elif 'nieuws ' in desc or 'nieuws ' in tdict['name']:
                                    tdict['genre'] = u'nieuws/actualiteiten'

                                elif 'sport' in desc or 'sport' in tdict['name']:
                                    tdict['genre'] = u'sport'

                                elif 'actualiteiten' in desc or 'actualiteiten' in tdict['name']:
                                    tdict['genre'] = u'nieuws/actualiteiten'


                            tdict['description'] = desc
                            desc_items = self.get_string_parts(desc)
                            for crole, cast in desc_items.items():
                                if len(cast) == 0:
                                    continue

                                elif crole in self.config.roletrans.keys():
                                    role = self.config.roletrans[crole]
                                    if not role in tdict['credits']:
                                        tdict['credits'][role] = []

                                    cast = re.sub('\) ([A-Z])', '), \g<1>', \
                                            re.sub(' & ', ', ', \
                                            re.sub(' en ', ', ', \
                                            re.sub('e\.a\.', '', cast[0])))).split(',')
                                    for cn in cast:
                                        tdict['credits'][role].append(cn.split('(')[0].strip())

                                elif self.config.write_info_files:
                                    self.config.infofiles.addto_detail_list(u'new oorboekje desc item => %s = %s' % (crole, cast))



                            # and append the program to the list of programs
                            tdict = self.check_title_name(tdict)
                            with self.source_lock:
                                self.program_data[chanid].append(tdict)



                    self.base_count += 1
                    self.day_loaded[0][offset] = True
                    # be nice to oorboekje.nl
                    time.sleep(random.randint(self.config.opt_dict['nice_time'][0], self.config.opt_dict['nice_time'][1]))

                if failure_count == 0 or retry == 1:
                    for chanid in self.channels.keys():
                        # Add starttime of the next program as the endtime
                        with self.source_lock:
                            self.program_data[chanid].sort(key=lambda program: (program['start-time']))
                            self.add_endtimes(chanid, 7)

                        self.parse_programs(chanid, 0, 'None')
                        self.channel_loaded[chanid] = True
                        self.config.channels[chanid].source_data[self.proc_id].set()
                        with self.source_lock:
                            for tdict in self.program_data[chanid]:
                                self.program_by_id[tdict['prog_ID'][self.proc_id]] = tdict

                        try:
                            self.config.infofiles.write_fetch_list(self.program_data[chanid], chanid, self.source, self.config.channels[chanid].chan_name, self.proc_id)

                        except:
                            pass

                    return

        except:
            self.config.log(['\n', 'An unexpected error has occured in the %s thread\n' %  (self.source), traceback.format_exc()], 0)
            for chanid in self.channels.keys():
                self.channel_loaded[chanid] = True
                self.config.channels[chanid].source_data[self.proc_id].set()

# end oorboekje_HTML

