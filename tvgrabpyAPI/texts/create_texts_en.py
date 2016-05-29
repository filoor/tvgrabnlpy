#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import pickle, io, os, sys

# If you like to create a translation, you do the following.
# - copy this file to a file with the two letter short for that language replacing "en".
# - also fill this two letter short in the lang variable below
# - replace the text strings with your language version, but:
#       - keep the '%' (%s, %d, etc) markers in place as they get replaced by things like the name of a file
#       - if there is an EOL '\n' at the end, leave it also in place, but also do not add your own
#       - keep any indentations at the start
#       - The first message texts[u'config][u'error'][-2] should contain the name of your language
# - run this new created script to create the langage file for your own use
# - send us this new created script and we probably include it with the language file in the package.
# - check regularily if you need to update the script, update the version and send us the updated version.

name = 'tv_grab_text'
version = (1, 0, 0)
lang = 'en'

def load_texts():
    texts = {
        u'config':{
            u'error':{
                -2: u'Loaded the English texts file\n',
                -1: u'Error creating message text! (%s, %s: %s)\n',
                0: u'Text message (%s, %s: %s) not Found!\n',
                1: u'Error updating to new Config.\n',
                2: u'Please remove the old config and Re-run me with the --configure flag.\n',
                3: u'Updated the configfile %s!\n',
                4: u'Check if you are fine with the settings.\n',
                5: u'If this is a first install, you have to enable the desired channels!\n',
                6: u'Creating config file: %s\n',
                7: u'Error writing new Config. Trying to restore an old one.\n',
                8: u'Created the configfile %s!\n',
                9: u'Updated the options in the configfile %s!\n',
                10: u'Sorry, thetvdb.com lookup is disabled!\n',
                11: u'Please supply a series title!\n',
                12: u'Invalid language code: "%s" supplied falling back to "nl"\n',
                13: u'An offset %s higher then the max is ridiculeous. We reset to %s',
                14: u'We can look a maximum of 14 days ahead. Resetting!\n',
                15: u'Creating %s directory,\n',
                16: u'Cannot write to outputfile: %s\n',
                17: u'Cannot access the config/log directory: %s\n',
                18: u'Cannot open the logfile: %s\n',
                19: u'Using config file: %s\n',
                20: u'Cannot write to cachefile: %s\n',
                21: u'Error accessing cachefile(directory): %s\n',
                22: u'Setting All to Fast Mode\n',
                23: u'Setting Channel: %s to Fast Mode\n',
                24: u'Using description length: %d for Cannel: %s\n',
                25: u'Maximum overlap 0 means overlap strategy set to: "%s"\n',
                26: u'Maximum overlap 0 means overlap strategy for Channel: %s set to: "%s"\n',
                27: u'Using Maximum Overlap: %d for Channel %s\n',
                28: u'overlap strategy for Channel: %s set to: "%s"\n',
                29: u'  A grabber that grabs tvguide data from multiple sources,\n',
                30: u'  combining the data into one XMLTV compatible listing.',
                31: u'Re-run me with the --configure flag.\n',
                32: u'Adding "legacy_xmltvids = True"\n',
                33: u'Run with "--configure" to make it permanent\n',
                34: u'Ignoring unknown section "%s"\n',
                35: u'Ignoring configuration line "%s". Outside any known section.\n',
                36: u'Error reading Config\n',
                37: u'Invalid line in Configuration section of config file %s:',
                38: u'Invalid line in Channels section of config file %s:',
                39: u'Channel section "%s" ignored. Unknown channel\n',
                40: u'Invalid line in %s section of config file %s:',
                41: u'Error reading the Defaults file %s\n',
                42: u'Error loading %s data from sourcematching.json!',
                43: u'Error reading the datafile on github.\n',
                44: u'Unable to continue with configure!\n',
                45: u'Invalid starttime for %s in combined channel: %s\nRemoving it!',
                46: u'Invalid endtime for %s in combined channel: %s\nRemoving it!',
                90: u'Invalid timezone for %s in combined channel: %s\nRemoving it!',
                47: u'We merged %s into %s\n',
                48: u'Since both were active, we have not set an alias\n',
                49: u'If you want to use the old chanid %s as xmltvid\n',
                50: u'you have to add:\n',
                51: u'to the channel configuration for %s\n',
                52: u'Since the old chanid was active, we have set an alias\n',
                53: u'to the channel configuration for %s\n',
                54: u'Since %s already has an xmltvid_alias set\n',
                55: u'we have not changed this.\n',
                56: u'If you want to use the old chanid %s as xmltvid\n',
                57: u'you have to change:\n',
                58: u'to:',
                59: u'in the channel configuration for %s\n',
                60: u'We could not check for any selfset options on the old chanid: %s\n',
                61: u'So check the settings for the new chanid: %s\n',
                62: u'Not all channel info could be retreived.\n',
                63: u'Try again in 15 minutes or so; or disable the failing source.\n',
                64: u'Source %s (%s) disabled',
                65: u'No detailfetches from Source %s (%s)',
                66: u'Channel specific settings other then the above (only for the active channels):',
                67: u'  prime_source setting: %s (%s) in sourcematching.json not used\n',
                68: u'  Source %s (%s) disabled\n',
                69: u'  Detail Source %s (%s) disabled\n',
                70: u'Error Opening the old config. Creating a new one.\n',
                71: u'Error reading the old config\n',
                72: u'Execution complete.\n',
                73: u'Fetch statistics for %s programms on %s channels:\n',
                74: u' Start time: %s\n',
                75: u'   End time: %s\n',
                76: u'   Duration: %s\n',
                77: u'%6.0f page(s) fetched, of which %s failed\n',
                78: u'%6.0f cache hits\n',
                79: u'%6.0f succesful ttvdb.com lookups\n',
                80: u'%6.0f    failed ttvdb.com lookups\n',
                81: u' Time/fetch: %s seconds\n',
                82: u'%6.0f page(s) fetched from theTVDB.com\n',
                83: u'%6.0f failure(s) on theTVDB.com\n',
                84: u'%6.0f   base page(s) fetched from %s\n',
                85: u'%6.0f detail page(s) fetched from %s\n',
                86: u'%6.0f failure(s) on %s\n',
                87: u'You can not run this script as root, except with --configure.\nIf you run --configure as root, the configuration is placed in\n"/etc/tvgrabpyAPI/" and used as fall-back configuration.\n',
                88: u'Trying to fall back on %s.\n',
                89: u'No valid source description for %s found. Disableing it!\n'},
            u'other':{
                1: u'The available sources are: ',
                2: u'The available detail sources are: ',
                3: u'The available logo sources are: ',
                4: u' 99: Your own full logo url',
                5: u'display version',
                6: u'prints a short description of the grabber',
                7: u'prints a long description in english of the grabber',
                8: u'xmltv required option',
                9: u'returns the preferred method to be called',
                10: u'returns the available sources',
                11: u'disable a numbered source.\nSee "--show-sources" for a list.',
                12: u'returns the available detail sources',
                13: u'returns the available logo sources',
                15: u'disable a numbered source for detailfetches.\nSee "--show-detail-sources" for a list.',
                16: u'disable fetching extra data from ttvdb.com.',
                17: u'Query ttvdb.com for a series-title and optionally store\nit with the ID in the DB. Enclose the title in quotes!\nOptionally add a language code after the title.\n',
                18: u'append tvgids.nl to the xmltv id\n(use this if you were using tv_grab_nl)',
                19: u'remove as in pre 2.2.8 for source 0 and 1 the sourceid\nfrom the chanid to get the xmltvid.',
                20: u'generate all data in UTC time (use with timezone "auto"\nin mythtv)',
                21: u'create configfile; rename an existing file to *.old.',
                22: u'After running configure, place all active channels in\na separate group on top of the list.\nOnly relevant together with the configure option.',
                23: u'name of the configuration file\n<default = "%s">',
                24: u'save the currently defined options to the config file\nadd options to the command-line to adjust the file.',
                25: u'cache descriptions and use the file to store\n<default = "%s">',
                26: u'clean the cache of outdated data before fetching',
                27: u'empties the program table before fetching data',
                28: u'empties the ttvdb table before fetching data',
                29: u'file where to send the output <default to the screen>',
                30: u'use for the outputfile Windows codeset (cp1252)\ninstead of utf-8',
                31: u'suppress all log output to the screen.',
                32: u'Sent log-info also to the screen.',
                33: u'do not grab details of programming from any of the\ndetail sources',
                34: u'<default> grab details of programming from one of the\ndetail sources',
                35: u'The day to start grabbing <defaults to 0 is today>',
                36: u'# number of days to grab from the several sources.\n<max 14 = default>\nWhere every source has itś own max.\n',
                38: u'number of days to grab slow and the rest in fast mode\nDefaults to all days possible',
                39: u'<default> insert urls to channel icons\n(mythfilldatabase will then use these)',
                40: u'do not insert urls to channel icons',
                41: u'mark HD programs,\ndo not set if you only record analog SD',
                42: u'<default> translate the grabbed genres into\nMythTV-genres. See the %s.set file',
                43: u'do not translate the grabbed genres into MythTV-genres.\nIt then only uses the basic genres without possibility\nto differentiate on subgenre.',
                44: u'maximum allowed length of program descriptions in\ncharacters.',
                45: u'what strategy to use to correct overlaps:\n"avarage" use average of stop and start of next program.\n          <default>\n"stop"    keep stop time of current program and adjust\n          start time.\n"start"   keep start time of next program and adjust\n          stop time.\n"none"    do not use any strategy and see what happens.\n',
                46: u'maximum length of overlap between programming to correct\n<default 10 minutes>',
                47: u'',
                48: u'',
                49: u'',
                50: u'# See: https://github.com/tvgrabbers/tvgrabnlpy/wiki/Over_de_configuratie\n',
                51: u'# This is a list with default options set by the --save-options (-O)\n',
                52: u'# argument. Most can be overruled on the commandline.\n',
                53: u'# Be carefull with manually editing. Invalid options will be\n',
                54: u'# silently ignored. Boolean options can be set with True/False,\n',
                55: u'# On/Off or 1/0. Leaving it blank sets them on. Setting an invalid\n',
                56: u'# value sets them off. You can always check the log for the used values.\n',
                57: u'# To edit you beter run --save-options with all the desired defaults.\n',
                58: u'# Options not shown here can not be set this way.\n',
                59: u'',
                60: u'',
                61: u'# DO NOT CHANGE THIS VALUE!\n',
                62: u'',
                63: u'# Set always_use_json to False to ignore Channelname, Channelgroup \n',
                64: u'# and prime_source set in sourcematching.json if they are set different\n',
                65: u'# in this configuration file. If you do not have set any of those yourself\n',
                66: u'# leave the value to True to profite from all updates.\n',
                67: u'',
                68: u'',
                69: u'# The following are tuning parameters. You normally do not need to change them.\n',
                70: u'# global_timeout is the maximum time in seconds to wait for a fetch to complete\n',
                71: u'#    before calling it a time-out failure.\n',
                72: u'# max_simultaneous_fetches is the maximum number of simultaneous fetches\n',
                73: u'#    that are allowed.\n',
                74: u'#    With the growing number of sources it is possible that they all together\n',
                75: u'#    try to get their page. This could lead to congestion and failure.\n',
                76: u'#    If you see often "incomplete read failures" or "get_page timed out", you\n',
                77: u'#    can try raising the first or lowering the second.\n',
                78: u'#    This won\'t significantly alter the total runtime as this is mostley determined\n',
                79: u'#    by the the highest number of fetches from a single source and the mandatory.\n',
                80: u'#    waittime in between those fetches to not overload their resources.\n',
                81: u'#    However all basepage fetches are retried on failure and a detailpagefailure\n',
                82: u'#    can triger a retry on one of the other detailsources. So a lot of failures\n',
                83: u'#    especially on source 0, 1 and 9 can increase the total runtime.\n',
                84: u'',
                85: u'',
                86: u'# This handles what goes to the log and screen\n',
                87: u'# 0 Nothing (use quiet mode to turns off screen output, but keep a log)\n',
                88: u'# 1 include Errors and Warnings\n',
                89: u'# 2 include page fetches\n',
                90: u'# 4 include (merge) summaries\n',
                91: u'# 8 include detail fetches and ttvdb lookups to the screen\n',
                92: u'# 16 include detail fetches and ttvdb lookups to the log\n',
                93: u'# 32 include matchlogging (see below)\n',
                94: u'# 64 Title renames\n',
                95: u'# 128 ttvdb failures\n',
                96: u'',
                97: u'',
                98: u'# What match results go to the log/screen (needs code 32 above)\n',
                99: u'# 0 = Log Nothing (just the overview)\n',
                100: u'# 1 = log not matched programs added\n',
                101: u'# 2 = log left over programs\n',
                102: u'# 4 = Log matches\n',
                103: u'# 8 = Log group slots\n',
                104: u'',
                105: u'',
                106: u'# Set "mail_log" to True to send the log to the mailaddress below\n',
                107: u'# Also set the mailserver and port apropriate\n',
                108: u'# SSL/startTLS is NOT sopported at present. Neither is authentication\n',
                109: u'# Make sure to first test on a console as mailing occures after \n',
                110: u'# closing of the logfile!\n',
                111: u'',
                112: u'',
                113: u'# Possible values for kijkwijzerstijl are:\n',
                114: u'#   long  : add the long descriptions and the icons\n',
                115: u'#   short : add the one word descriptions and the icons\n',
                116: u'#   single: add a single string (mythtv only reads the first item)\n',
                117: u'#   none  : don\'t add any\n',
                118: u'',
                119: u'',
                120: u'# These are the channeldefinitions. You can disable a channel by placing\n',
                121: u'# a \'#\' in front. Seperated by \';\' you see on every line: The Name,\n',
                122: u'# the group, the channelID, the ID\'s for the sources in the order as\n',
                123: u'# returned by the "--show-sources" option and finally the iconsource and name.\n',
                124: u'# You can change the names to suit your own preferences.\n',
                125: u'# A missing ID means the source doesn\'t supply the channel.\n',
                126: u'# Removing an ID disables fetching from that source, but keep the \';\'s in place.\n',
                127: u'# But you better use the "disable_source" option as described below.\n',
                128: u'# Set iconsource to 99, to add your own full url.\n',
                129: u'#\n',
                130: u'# To specify further Channel settings you can add sections in the form of\n',
                131: u'# [Channel <channelID>], where <channelID> is the third item on the line,\n',
                132: u'# You can use the following tags:\n',
                133: u'# Boolean values (True, 1, on or no value means True. Everything else False):\n',
                134: u'#   fast, compat, legacy_xmltvids, logos, cattrans, mark_hd, add_hd_id,\n',
                135: u'#   append_tvgidstv, disable_ttvdb, use_split_episodes\n',
                136: u'#     append_tvgidstv is True by default, which means: \'Don\'t get data\n',
                137: u'#     from tvgids.tv if there is from tvgids.nl\' tvgids.tv data normally is\n',
                138: u'#     inferiour, except for instance that for Veronica it fills in Disney XD\n',
                139: u'#     add_hd_id: if set to True will create two listings for the given channel.\n',
                140: u'#     One normal one without HD tagging and one with \'-hd\' added to the ID\n',
                141: u'#     and with the HD tags. This will overrule any setting of mark_hd\n',
                142: u'# Integer values:\n',
                143: u'#   slowdays, max_overlap, desc_length, prime_source, prefered_description\n',
                144: u'#   disable_source, disable_detail_source\n',
                145: u'#     prime_source (0-12) is the source whose timings and titles are dominant\n',
                146: u'#     It defaults to 2 for rtl channels, 4 for NPO channels, 5 for Dutch regional\n',
                147: u'#     and 6 for group 2 and 9 (Flemmisch) channels or else the first available\n',
                148: u'#     source as set in sourcematching.json (2, 4, 7, 0, 5, 1, 9, 6, 8)\n',
                149: u'#     prefered_description (0-12) is the source whose description, if present,\n',
                150: u'#     is used. It defaults to the longest description found.\n',
                151: u'#     with disable_source and disable_detail_source you can disable a source\n',
                152: u'#     for that channel either al together or only for the detail fetches\n',
                153: u'#     disabling an unavailable source has no effect.\n',
                154: u'#     With the commandline options: "--show-sources" and "--show-detail-sources"\n',
                155: u'#     you can get a list of available sources and their ID\n',
                156: u'# String values:\n',
                157: u'#   overlap_strategy (With possible values): \n',
                158: u'#     average, stop, start; everything else sets it to none\n',
                159: u'#   xmltvid_alias: This is a string value to be used in place of the chanid\n',
                160: u'#     for the xmltvID. Be careful not to set it to an existing chanid.\n',
                161: u'#     It can get set by configure on chanid changes! See also the WIKI\n',
                162: u'\n',
                163: u'',
                }},
        u'IO':{
            u'error':{
                21: u'An unexpected error has occured in the %s thread:\n',
                22: u'An unexpected error has occured:\n',
                4: u'If you want assistence, please attach your configuration and log files!\n',
                5: u'Unrecognized log-message: %s of type %s\n',
                8: u'Verifying the database\n',
                6: u'Cache function disabled!\n',
                7: u'The cache directory is not accesible. Cache function disabled!\n',
                9: u'Error loading the database: %s.db (possibly corrupt)\n',
                10: u'Trying to load a backup copy',
                11: u'Failed to load the database: %s.db\n',
                12: u'Disableing Cache function',
                13: u'Error creating the %s table!\n',
                14: u'Error updating the %s table with collumn "%s"!\n',
                15: u'Error updating the %s table with Index "%s"!\n',
                16: u'Error loading old cache file: %s (possibly corrupt)\n',
                17: u'Converting the old pickle cache to sqlite.\n',
                18: u'This may take some time!\n',
                19: u'Added %s program records to the database.\n',
                20: u'Error saving program %s to the database.\n',
                1: u'File: "%s" not found or could not be accessed.\n',
                2: u'%s is not encoded in %s.\n',
                3: u'%s has invalid encoding %s.\n'},
            u'stats':{
                1: u'   Add',
                2: u' Merge',
                3: u'adding',
                4: u'merging',
                5: u' source',
                6: u'channel',
                7: u'Now %s %s programs from %s into %s programs from %s\n',
                8: u'    (channel %s of %s)',
                9: u'%s statistics for %s (channel %s of %s)\n         from %s %s\n',
                10: u'%7.0f programs in %s for range: %s - %s\n    (%2.0f groupslots),\n',
                11: u'%7.0f programs in %s for range: %s - %s\n',
                12: u'%7.0f programs added new\n',
                13: u'%7.0f programs generically matched on name to get genre\n',
                14: u'%7.0f programs matched on time and name\n',
                15: u'%7.0f programs added to group slots\n',
                16: u'%7.0f programs left unmatched in %s\n',
                17: u'Now%4.0f programs of which %2.0f groupslots\n',
                18: u'and%4.0f without genre.\n',
                19: u'Detail'
            },
            u'other':{
                u'': u''}},
        u'fetch':{
            u'error':{
                1: u'get_page timed out on (>%s s): %s\n',
                2: u'An unexpected error "%s:%s" has occured while fetching page: %s\n',
                3: u'Cannot open url %s\n',
                4: u'Cannot parse url %s: code=%s\n',
                5: u'get_page timed out on (>%s s): %s\n',
                68: u'Error parsing the %spage description for source: %s\n',
                71: u'Error reading the %spage for source: %s\n',
                69: u'Error processing %s-function %s for source %s\n',
                70: u'The supplied data was: %s\n',
                6: u'Error retreiving episodes from theTVDB.com\n',
                7: u'Error retreiving an ID from theTVdb.com\n',
                8: u'  No ttvdb id for "%s" on channel %s\n',
                9: u'ttvdb lookup for "%s: %s"\n',
                10: u'ttvdb failure for "%s: %s" on channel %s\n',
                11: u'Channel %s seems to be waiting for %s lost detail requests from %s.\n',
                12: u'Setting it to ready\n',
                13: u'Fatal Error processing the basepages from %s\n',
                14: u'Setting them all to being loaded, to let the other sources finish the job\n',
                15: u'Error processing the detailpage: %s\n',
                16: u'Error processing the json detailpage: http://www.tvgids.nl/json/lists/program.php?id=%s\n',
                17: u'[fetch failed or timed out] %s:(%3.0f%%) %s\n',
                18: u'      [cached] %s:(%3.0f%%) %s\n',
                19: u'[%s fetch] %s:(%3.0f%%) %s\n',
                20: u'Removing "%s" from "%s"\n',
                21: u'Renaming "%s" to "%s"\n',
                22: u'Oops, "%s" has no end time. Trying to fix...\n',
                23: u'Deleting invalid stop/start time: %s\n',
                24: u'Deleting duplicate: %s\n',
                25: u'Deleting grouping/broadcaster: %s\n',
                26: u'"%s" and "%s" overlap %s minutes. Adjusting times.\n',
                27: u'"%s" and "%s" have gap of %s minutes. Adjusting times.\n',
                31: u'',
                32: u'',
                33: u'',
                34: u'',
                35: u'',
                36: u'',
                37: u'',
                38: u'',
                39: u'',
                40: u'%6.0f programs left in %s to match\n',
                41: u'',
                42: u'',
                43: u'%6.0f programs matched on time and genre\n',
                44: u'',
                45: u'%6.0f programs added unmatched from info\n',
                28: u'Match details:\n',
                29: u'title match: ',
                30: u'genre match: ',
                46: u'added from info',
                47: u'groupslot in ',
                48: u'added from ',
                49: u'groupslot in info',
                50: u'left over in ',
                51: u'No Data from %s for channel: %s\n',
                52: u'Detail sources: %s died.\n',
                53: u'So we stop waiting for the pending details for channel %s\n',
                54: u'Detail statistics for %s (channel %s of %s)\n',
                55: u'%6.0f cache hit(s)\n',
                56: u'%6.0f without details in cache\n',
                57: u'%6.0f succesful ttvdb lookups\n',
                58: u'%6.0f    failed ttvdb lookups\n',
                59: u'%6.0f detail fetch(es) from %s.\n',
                60: u'%6.0f failure(s)\n',
                61: u'%6.0f without detail info\n',
                62: u'%6.0f left in the %s queue to process\n',
                63: u'Now Checking cache for %s programs on %s(xmltvid=%s%s)\n',
                64: u'    (channel %s of %s) for %s days.\n',
                65: u'Now fetching details for %s programs on %s(xmltvid=%s%s)\n',
                66: u'    [no fetch] %s:(%3.0f%%) %s\n',
                67: u'Splitting title "%s"\n'},
            u'error2':{
                11: u'Channel %s seems to be waiting for %s lost detail requests from %s.\n',
                12: u'Setting it to ready\n',
                18: u'      [cached] %s:(%3.0f%%) %s\n',
                15: u'Error processing the detailpage: %s\n',
                16: u'Error processing the json detailpage: http://www.tvgids.nl/json/lists/program.php?id=%s\n',
                17: u'[fetch failed or timed out] %s:(%3.0f%%) %s\n',
                19: u'[%s fetch] %s:(%3.0f%%) %s\n',
                68: u'Error parsing the %spage description for source: %s\n',
                13: u'Fatal Error processing the basepages from %s\n',
                14: u'Setting them all to being loaded, to let the other sources finish the job\n',
                20: u'Removing "%s" from "%s"\n',
                39: u'%6.0f programs added outside common timerange\n',
                40: u'%6.0f programs left in %s to match\n',
                41: u'%6.0f programs generically matched on name to get genre\n',
                21: u'Renaming "%s" to "%s"\n',
                22: u'Oops, "%s" has no end time. Trying to fix...\n',
                23: u'Deleting invalid stop/start time: %s\n',
                24: u'Deleting duplicate: %s\n',
                25: u'Deleting grouping/broadcaster: %s\n',
                26: u'"%s" and "%s" overlap %s minutes. Adjusting times.\n',
                27: u'"%s" and "%s" have gap of %s minutes. Adjusting times.\n',
                28: u'Match details:\n',
                29: u'title match: ',
                30: u'genre match: ',
                31: u'Now merging %s (channel %s of %s):\n',
                32: u'  %s programs from %s into %s programs from %s\n',
                33: u'Merg statistics for %s (channel %s of %s) from %s into %s\n',
                34: u'Now merging %s programs from %s into %s programs from %s\n',
                35: u'    (channel %s of %s)',
                36: u'Merg statistics for %s (channel %s of %s) from %s\n',
                37: u'%6.0f programs in %s for range: %s - %s, \n',
                38: u'%6.0f programs in %s for range: %s - %s\n',
                46: u'added from info',
                48: u'added from ',
                39: u'%6.0f programs added outside common timerange\n',
                40: u'%6.0f programs left in %s to match\n',
                41: u'%6.0f programs generically matched on name to get genre\n',
                47: u'groupslot in ',
                49: u'groupslot in info',
                42: u'%6.0f programs matched on time and name\n',
                43: u'%6.0f programs matched on time and genre\n',
                44: u'%6.0f details  added from group slots\n',
                45: u'%6.0f programs added unmatched from info\n',
                50: u'left over in ',
                },
            u'other':{
                1: u'  Downloading %s.json...\n',
                u'': u''}},
        u'sources':{
            u'error':{
                1: u'Unable to get channel info from %s\n',
                31: u'An error ocured while reading %s channel info.\n',
                13: u'Now fetching %s(xmltvid=%s%s) from %s\n',
                23: u'    (channel %s of %s) for day %s of %s.\n',
                34: u'    (channel %s of %s) for %s days.\n',
                17: u'    (channel %s of %s) for periode %s of %s).\n',
                14: u'    (channel %s of %s) for %s days, page %s.\n',
                2: u'Now fetching %s channel(s) from %s\n',
                47: u'Now fetching the %s channelgroup from %s\n',
                3: u'    for day %s of %s.\n',
                11: u'    for %s days.\n',
                43: u'    for periode %s of %s.',
                44: u'    for %s days, page %s.\n',
                20: u'Skip channel %s on %s!, day=%d. No data\n',
                35: u'Skip channel %s on %s!. No data',
                18: u'Skip channel %s on %s!, periode=%d. No data\n',
                15: u'Skip channel %s on %s!, page=%d. No data\n',
                4: u'Skip day %d on %s. No data\n',
                12: u'Skip %s. No data\n',
                45: u'Skip periode %d on %s. No data\n',
                46: u'Skip page %d on %s. No data\n',
                48: u'Skip channelgroup %s on %s!, day=%d. No data\n',
                49: u'Skip channelgroup %s on %s!. No data',
                50: u'Skip channelgroup %s on %s!, periode=%d. No data\n',
                51: u'Skip channelgroup %s on %s!, page=%d. No data\n',
                22: u'Unable to veryfy the right offset.\n',
                21: u'Skip channel=%s on %s!, day=%d. Wrong date!\n',
                6: u'Can not determine program title for "%s" on channel: %s, source: %s\n',
                7: u'Can not determine timings for "%s" on channel: %s, source: %s\n',
                40: u'',
                41: u'',
                42: u'',
                8: u'Page %s returned no data\n',
                9: u'Fetching page %s returned an error:\n',
                10: u'Error processing the description from: %s\n',
                28: u'Error Fetching detailpage %s\n',
                30: u'Error processing %s detailpage:%s\n'},

                16: u'No data on %s %s-page for day=%d attempt %s\n',
                25: u'No data on %s for %s, day=%d!\n',
                5: u'Unsubscriptable content from channel url: %r\n',
                19: u'Error: "%s" reading the %s basepage for channel=%s, week=%d.\n',
                24: u'Error: "%s" reading the %s basepage for channel=%s, day=%d.\n',
                36: u'Error: "%s" reading the %s basepage for channel=%s.\n',
                38: u'Error: "%s" reading the %s basepage for day=%s.\n',
                37: u'Skip day=%s on %s. No data!\n',
                39: u'Skip day=%d on %s. Wrong date.',
                33: u'Error validating page for day:%s on %s. Wrong date!\n',
                26: u'Error extracting ElementTree for channel:%s day:%s on %s\n',
                29: u'Error extracting ElementTree from:%s on %s\n',
                32: u'Error extracting ElementTree for day:%s on %s\n',
                27: u'Error processing %s data for channel:%s day:%s\n',
            u'tvgids.nl':{
                1: u'More then 2 sequential Cooky block pages encountered. Falling back to json\n'},
            u'tvgids.tv':{
                1: u'   We assume further pages to be empty!\n',
                2: u'Possibly an incomplete pagefetch. Retry in the early morning after 4/5 o\'clock.\n'},
            u'other':{
                u'': u''}}}
    return texts
                #~ 0: u'',
                #~ 1: u'',
                #~ 2: u'',
                #~ 3: u'',
                #~ 4: u'',
                #~ 5: u'',
                #~ 6: u'',
                #~ 7: u'',
                #~ 8: u'',
                #~ 9: u'',

def create_pickle(texts):
    fle_name = u'%s/%s.%s' % (os.path.abspath(os.curdir), name, lang)

    if os.path.isfile(fle_name):
        print(u'The language file %s already exists.\nDo you want to overwrite it [Y|N]?' % fle_name)
        while True:
            x = sys.stdin.read(1)
            if x in ('n', 'N'):
                print(u'Exiting')
                sys.exit(0)

            elif x in ('Y', 'y'):
                break

        os.remove(fle_name)

    print(u'Writing %s language file' % lang)
    fle = open(fle_name, 'w')
    text_dict = {}
    text_dict['lang'] = lang
    text_dict['version'] = version
    text_dict['texts'] = texts
    pickle.dump(text_dict, fle)

def main():
    texts = load_texts()
    create_pickle(texts)

# allow this to be a module
if __name__ == '__main__':
    sys.exit(main())
