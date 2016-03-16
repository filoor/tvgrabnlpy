#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Python 3 compatibility
from __future__ import unicode_literals
# from __future__ import print_function

description_text = """
    SYNOPSIS

    tv_grab_nl_py is a python script that trawls tvgids.nl for TV
    programming information and outputs it in XMLTV-formatted output (see
    http://membled.com/work/apps/xmltv). Users of MythTV
    (http://www.mythtv.org) will appreciate the output generated by this
    grabber, because it fills the category fields, i.e. colors in the EPG,
    and has logos for most channels automagically available. Check the
    website below for screenshots.  The newest version of this script can be
    found here:

         https://github.com/tvgrabbers/tvgrabnlpy/

    USAGE

    Check the web site above and/or run script with --help and start from there

    REQUIREMENTS

    * Python 2.6 or 2.7
    * Connection with the Internet

    QUESTIONS

    Questions (and patches) are welcome at:
    http://www.pwdebruin.net/mailman/listinfo/tv_grab_nl_py_pwdebruin.net
    https://github.com/tvgrabbers/tvgrabnlpy/issues
    https://groups.google.com/forum/#!forum/tvgrabnlpy

    UPGRADE NOTES

    If you were using tv_grab_nl from the XMLTV bundle then enable the
    compat flag or use the --compat command-line option.  Otherwise, the
    xmltvid's are wrong and you will not see any new data in MythTV.

    HISTORY

    tv_grab_nl_py used to be called tv_grab_nl_pdb, created by Paul de Bruin
    and first released on 2003/07/09. At the same time the code base switched
    from using CVS to SVN at Google Code, and as a result the version numbering
    scheme has changed. The lastest official release of tv_grab_nl_pdb is 0.48.
    The first official release of tv_grab_nl_py is 6. In 2012, The codebase
    moved to Git, and the version number was changed once more. The latest
    subversion release of tv_grab_nl_py is r109. The first Git release of
    tv_grab_nl_py is 2012-03-11 12:03.

    As of december 2014/ januari 2015 Version 2.0.0:
      Upgrading argument processing from getopt to argparse.
      Also adding some options and adding to help text.
      Fixing a small bug preventing multiple word details like 'jaar van
        premiere' from being proccessed.
      Adding genre/subgenre translation table and file (tv_grab_nl_py.set).
        Automatically adding new genre/subgenre combinations on every scan.
        Still looking into the way MythTV handles this.
        This contains also other translation tables which mostly get updated on
        every scan and gets created with defaults if not existing.
      Adding titlesplit exception list to tv_grab_nl_py.set. Especially for
        spin-off series like 'NCIS: Los Angeles'.
      Adding optional default options file and creation.  (tv_grab_nl_py.opt)
      Adding optional proccessing of HD attribute.
      Adding session log function (to the self.configname with .log added)
        the last log is saved to .old (like with .conf, .opt and .set files)
      Adding rtl.nl lookup for the 7 RTL channels. This adds season/episode info
        and lookup further than 4 days in the future, defaulting to 14 days.
        Genre info is missing. Timing and description from rtl.nl is used over
        tvgids.nl
      Adding  teveblad.be lookup, mainly for belgium channels. This adds
        season/episode info and lookup up to 7 days. Dutch channels only
        have prime-time info and the commercial channels are missing.
        Genre info is basic. Timing for the Belgium channels is used over
        tvgids.nl
      Adding tvgids.tv lookup. This adds lookup up to 14 days with decent genre
        info.
      Merged tv_grab_nl_py.opt into tv_grab_nl_py.conf and added several
        translation tables to tv_grab_nl_py.set.
      Moving html proccessing from pure regex filtering to ElementTree
      Reorganised code to be more generic to make adding new sources easer
        and as preparation for a self.configuration module. Also put the different
        sources in parallel threads.
      Working on more intelligent description proccessing.
      Working in ever more intelligent source merging.
      Working on a self.configuration module.
      Possibly adding ttvdb.com and tmdb3.com lookup for missing descriptions
        and season/episode info
      Possibly adding more optional (foreign) sources (atlas?)

    CONTRIBUTORS

    Main author: Paul de Bruin (paul at pwdebruin dot net)
    Current maintainer: Freek Dijkstra (software at macfreek dot nl)
    Currently 'december 2014' the latest version of '2012-03-27' adapted by:
    Hika van den Hoven hikavdh at gmail dot com, but also active on the
    mythtv list: mythtv-users at mythtv dot org

    Michel van der Laan made available his extensive collection of
    high-quality logos that is used by this script.

    Several other people have provided feedback and patches:
    Huub Bouma, Michael Heus, Udo van den Heuvel, Han Holl, Hugo van der Kooij,
    Roy van der Kuil, Ian Mcdonald, Dennis van Onselen, Remco Rotteveel, Paul
    Sijben, Willem Vermin, Michel Veerman, Sietse Visser, Mark Wormgoor.

    LICENSE

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# Modules we need
import sys, locale, traceback, json
import time, datetime, pytz
import tv_grab_config
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
        self.name ='tv_grab_nl_py3'
        self.datafile = 'tv_grab_nl.json'
        tv_grab_config.Configure.__init__(self)
        # Version info as returned by the version function
        self.country = 'The Netherlands'
        self.description = 'Dutch/Flemish grabber combining multiple sources.'
        self.major = 3
        self.minor = 0
        self.patch = 0
        self.patchdate = u'20160316'
        self.alfa = True
        self.beta = True
        self.output_tz = pytz.timezone('Europe/Amsterdam')

    def init_sources(self):
        tv_grab_config.Configure.init_sources(self)
        #~ self.channelsource[0] = sources.tvgids_JSON(self, 0, 'source-tvgids.nl', 1)
        #~ self.channelsource[1] = sources.tvgidstv_HTML(self, 1, 'source-tvgids.tv', 2)
        #~ self.channelsource[9] = sources.primo_HTML(self, 9, 'source-primo.eu', 1)

# end Configure()
config = Configure()

def main():
    # We want to handle unexpected errors nicely. With a message to the log
    try:
        # Get the options, channels and other configuration
        start_time = datetime.datetime.now()
        x = config.validate_commandline()
        if x != None:
            return(x)

        config.log("The Netherlands: %s\n" % config.version(True), 1, 1)
        config.log('Start time of this run: %s\n' % (start_time.strftime('%Y-%m-%d %H:%M')),4, 1)

        # Start the seperate fetching threads
        for source in config.channelsource.values():
            x = source.start()
            if x != None:
                return(x)

        # Start the Channel threads, but wait a second so the sources have properly initialized any child channel
        time.sleep(1)
        counter = 0
        channel_threads = []
        for channel in config.channels.values():
            if not (channel.active or channel.is_child):
                continue

            counter += 1
            channel.counter = counter
            x = channel.start()
            if x != None:
                return(x)

            channel_threads.append(channel)

        # Synchronize
        for index in (0, 1):
            config.channelsource[index].join()

        for channel in channel_threads:
            if channel.is_alive():
                channel.join()

        # produce the results and wrap-up
        config.write_defaults_list()
        config.xml_output.print_string()

        # Create a report
        end_time = datetime.datetime.now()
        config.write_statistics(start_time, end_time)

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
