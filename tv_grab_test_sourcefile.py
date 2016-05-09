#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Python 3 compatibility
from __future__ import unicode_literals
# from __future__ import print_function

# Modules we need
import sys, locale, traceback, json
import time, datetime, pytz
import tv_grab_config, tv_grab_fetch
try:
    unichr(42)
except NameError:
    unichr = chr    # Python 3

# check Python version
if sys.version_info[:3] < (2,7,9):
    sys.stderr.write("tv_grab_nl_py requires Pyton 2.7.9 or higher\n")
    sys.exit(2)

if sys.version_info[:2] >= (3,0):
    sys.stderr.write("tv_grab_nl_py does not yet support Pyton 3 or higher.\nExpect errors while we proceed\n")

locale.setlocale(locale.LC_ALL, '')

if tv_grab_config.Configure().version()[1:4] < (1,0,0):
    sys.stderr.write("tv_grab_nl_py requires tv_grab_config 1.0.0 or higher\n")
    sys.exit(2)

class Configure(tv_grab_config.Configure):
    def __init__(self):
        self.name ='tv_grab_nl_py'
        self.datafile = 'tv_grab_nl.json'
        self.compat_text = '.tvgids.nl'
        tv_grab_config.Configure.__init__(self)
        # Version info as returned by the version function
        self.country = 'The Netherlands'
        self.description = 'Dutch/Flemish grabber combining multiple sources.'
        self.major = 3
        self.minor = 0
        self.patch = 0
        self.patchdate = u'20160208'
        self.alfa = True
        self.beta = True
        self.output_tz = pytz.timezone('Europe/Amsterdam')
        self.combined_channels_tz = pytz.timezone('Europe/Amsterdam')


# end Configure()
config = Configure()

def read_commandline(self):
    description = u"%s: %s\n" % (self.country, self.version(True)) + \
                    u"The Netherlands: %s\n" % self.version(True, True) + \
                    self.text('config', 29) + self.text('config', 30)

    parser = argparse.ArgumentParser(description = description, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-V', '--version', action = 'store_true', default = False, dest = 'version',
                    help = self.text('config', 5, type='other'))

    parser.add_argument('-C', '--config-file', type = str, default = self.opt_dict['config_file'], dest = 'config_file',
                    metavar = '<file>', help =self.text('config', 23, (self.opt_dict['config_file'], ), type='other'))

def main():
    # We want to handle unexpected errors nicely. With a message to the log
    try:
        #~ site_tz = pytz.timezone('Europe/Amsterdam')
        #~ current_date = datetime.datetime.now(site_tz).toordinal()
        #~ for offset in range(14):
            #~ weekday = int(datetime.date.fromordinal(current_date + offset).strftime('%w'))
            #~ first_day = offset + 2 - weekday
            #~ if weekday < 2:
                #~ first_day -= 7
            #~ print weekday, first_day, datetime.date.fromordinal(current_date + first_day).strftime('%Y%m%d')


        #~ channel ='een'
        #~ source = tv_grab_fetch.FetchData(config, 11, 'source-virtual.nl')

        channel = 'npo-radio-1'
        source = tv_grab_fetch.FetchData(config, 12, 'source-oorboekje.nl')
        #~ source = tv_grab_fetch.FetchData(config, 2, 'source-rtl.nl')
        #~ channel ='een'
        #~ source = tv_grab_fetch.FetchData(config, 8, 'source-nieuwsblad.be')
        #~ source = tv_grab_fetch.FetchData(config, 7, 'source-vpro.nl', 2)
        #~ source = tv_grab_fetch.FetchData(config, 4, 'source-npo.nl', 1)
        #~ channel ='24443943184'
        #~ source = tv_grab_fetch.FetchData(config, 5, 'source-horizon.tv', 1)
        #~ source = tv_grab_fetch.FetchData(config, 6, 'source-humo.be', 1)
        #~ channel ='O8'
        #~ source = tv_grab_fetch.FetchData(config, 10, 'source-vrt.be', 1)

        #~ channel = '5'
        #~ source = tv_grab_fetch.FetchData(config, 0, 'source-tvgids.nl', 0)
        #~ channel ='nederland-1'
        #~ source = tv_grab_fetch.FetchData(config, 1, 'source-tvgids.tv', 3)
        #~ channel = 'npo1'
        #~ channel ='een'
        #~ source= tv_grab_fetch.FetchData(config, 9, 'source-primo.eu', 1)

        config.validate_option('config_file')
        config.get_sourcematching_file()

        source.test_output = sys.stdout
        #~ source.print_tags = True
        #~ source.print_roottree = True
        #~ source.show_parsing = True
        source.print_searchtree = True
        source.show_result = True

        sid = source.proc_id
        config.channelsource[sid] = source
        config.channelsource[sid].init_channel_source_ids()
        tdict = config.fetch_func.checkout_program_dict()
        #~ tdict['channelid'] = config.channelsource[sid].chanids[channel]

        #~ config.channelsource[sid].get_channels()

        data = config.channelsource[sid].get_page_data('base',{'offset': 0, 'channel': channel, 'channelgrp': 'rest', 'cnt-offset': 0, 'start':0, 'days':4})
        config.channelsource[sid].parse_basepage(data, {'offset': 1, 'channel': channel, 'channelgrp': 'main'})

        #~ tdict['detail_url'][sid] = 'midsomer-murders/15170844'
        #~ config.channelsource[sid].load_detailpage('detail', tdict)

        #20091598
        #20091569
        #20054611
        #20091568

        #tussen-kunst-en-kitsch/15170469
        #nos-sportjournaal/15170466
        #midsomer-murders/15170844

        #6526944
        #6526945
        #6526950

    except:
        traceback.print_exc()
        #~ config.logging.log_queue.put({'fatal': [traceback.format_exc(), '\n'], 'name': None})
        return(99)

    # and return success
    return(0)
# end main()

# allow this to be a module
if __name__ == '__main__':
    x = main()
    config.close()
    sys.exit(x)