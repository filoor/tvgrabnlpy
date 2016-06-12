#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Python 3 compatibility
from __future__ import unicode_literals
# from __future__ import print_function

import codecs, locale, re, os, sys, io, shutil, difflib
import traceback, smtplib, sqlite3
import datetime, calendar, pytz
import tv_grab_channel
from threading import Thread, Lock, RLock
from Queue import Queue, Empty
from copy import deepcopy, copy
from email.mime.text import MIMEText
from xml.sax import saxutils


class Functions():
    """Some general IO functions"""

    def __init__(self, config):
        self.default_file_encoding = 'utf-8'
        self.encoding = None
        self.configversion = None
        self.config = config
        self.logging = config.logging

    # end init()

    def log(self, message, log_level = 1, log_target = 3):
        if self.logging == None:
            return

        # If logging not (jet) available, make sure important messages go to the screen
        if (self.logging.log_output == None) and (log_level < 2) and (log_target & 1):
            if isinstance(message, (str, unicode)):
                sys.stderr.write(message.encode(self.logging.local_encoding, 'replace'))

            elif isinstance(message, (list ,tuple)):
                for m in message:
                    sys.stderr.write(m.encode(self.logging.local_encoding, 'replace'))

            if log_target & 2:
                self.logging.log_queue.put([message, log_level, 2])

        else:
            self.logging.log_queue.put([message, log_level, log_target])

    # end log()

    def save_oldfile(self, fle, save_ext='old'):
        """ save the old file to .old if it exists """
        save_fle = '%s.%s' % (fle, save_ext)
        if os.path.isfile(save_fle):
            os.remove(save_fle)

        if os.path.isfile(fle):
            os.rename(fle, save_fle)

    # end save_oldfile()

    def restore_oldfile(self, fle, save_ext='old'):
        """ restore the old file from .old if it exists """
        save_fle = '%s.%s' % (fle, save_ext)
        if os.path.isfile(fle):
            os.remove(fle)

        if os.path.isfile(save_fle):
            os.rename(save_fle, fle)

    # end save_oldfile()

    def open_file(self, file_name, mode = 'rb', encoding = None):
        """ Open a file and return a file handler if success """
        if encoding == None:
            encoding = self.default_file_encoding

        if 'r' in mode and not (os.path.isfile(file_name) and os.access(file_name, os.R_OK)):
            self.log(self.config.text('IO', 1, (file_name, )))
            return None

        if ('a' in mode or 'w' in mode):
            if os.path.isfile(file_name) and not os.access(file_name, os.W_OK):
                self.log(self.config.text('IO', 1, (file_name, )))
                return None

        try:
            if 'b' in mode:
                file_handler =  io.open(file_name, mode = mode)
            else:
                file_handler =  io.open(file_name, mode = mode, encoding = encoding)

        except IOError as e:
            if e.errno == 2:
                self.log(self.config.text('IO', 1, (file_name, )))
            else:
                self.log('File: "%s": %s.\n' % (file_name, e.strerror))
            return None

        return file_handler

    # end open_file ()

    def get_line(self, fle, byteline, isremark = False, encoding = None):
        """
        Check line encoding and if valid return the line
        If isremark is True or False only remarks or non-remarks are returned.
        If None all are returned
        """
        if encoding == None:
            encoding = self.default_file_encoding

        try:
            line = byteline.decode(encoding)
            line = line.lstrip()
            line = line.replace('\n','')
            if isremark == None:
                return line

            if len(line) == 0:
                return False

            if isremark and line[0:1] == '#':
                return line

            if not isremark and not line[0:1] == '#':
                return line

        except UnicodeError:
            self.log(self.config.text('IO', 2, (fle.name, encoding)))

        return False

    # end get_line()

    def check_encoding(self, fle, encoding = None, check_version = False):
        """
        Check file encoding. Return True or False
        Encoding is stored in self.encoding
        Optionally check for a version string
        and store it in self.configversion
        """
        # regex to get the encoding string
        reconfigline = re.compile(r'#\s*(\w+):\s*(.+)')

        self.encoding = None
        self.configversion = None

        if encoding == None:
            encoding = self.default_file_encoding

        for byteline in fle.readlines():
            line = self.get_line(fle, byteline, True, self.encoding)
            if not line:
                continue

            else:
                match = reconfigline.match(line)
                if match is not None and match.group(1) == "encoding":
                    encoding = match.group(2)

                    try:
                        codecs.getencoder(encoding)
                        self.encoding = encoding

                    except LookupError:
                        self.log(self.config.text('IO', 3, (fle.name, encoding)))
                        return False

                    if (not check_version) or self.configversion != None:
                        return True

                    continue

                elif match is not None and match.group(1) == "configversion":
                    self.configversion = float(match.group(2))
                    if self.encoding != None:
                        return True

                continue

        if check_version and self.configversion == None:
            fle.seek(0,0)
            for byteline in fle.readlines():
                line = self.get_line(fle, byteline, False, self.encoding)
                if not line:
                    continue

                else:
                    config_title = re.search('[(.*?)]', line)
                    if config_title != None:
                        self.configversion = float(2.0)
                        break

            else:
                self.configversion = float(1.0)

        if self.encoding == None:
            return False

        else:
            return True

    # end check_encoding()


# end Functions()

class Logging(Thread):
    """
    The tread that manages all logging.
    You put the messages in a queue that is sampled.
    So logging can start after the queue is opend when this class is called
    Before the fle to log to is known
    """
    def __init__(self, config):
        Thread.__init__(self)
        self.quit = False
        self.config = config
        self.functions = Functions(config)
        self.log_queue = Queue()
        self.log_output = None
        self.log_string = []
        try:
            codecs.lookup(locale.getpreferredencoding())
            self.local_encoding = locale.getpreferredencoding()

        except LookupError:
            if os.name == 'nt':
                self.local_encoding = 'windows-1252'

            else:
                self.local_encoding = 'utf-8'

    # end init()

    def run(self):
        self.log_output = self.config.log_output
        self.fatal_error = [self.config.text('IO', 4), \
                '     %s\n' % (self.config.opt_dict['config_file']), \
                '     %s\n' % (self.config.opt_dict['log_file'])]

        while True:
            try:
                if self.quit and self.log_queue.empty():
                    # We close down after mailing the log
                    if self.config.opt_dict['mail_log']:
                        self.send_mail(self.log_string, self.config.opt_dict['mail_log_address'])

                    return(0)

                try:
                    message = self.log_queue.get(True, 5)

                except Empty:
                    continue

                if message == None:
                    continue

                elif isinstance(message, dict) and 'fatal' in message:
                    # A fatal Error has been received, after logging we send all threads the quit signal
                    if 'name'in message and message['name'] != None:
                        mm =  ['\n', self.config.text('IO', 21, (message['name'], ))]

                    else:
                        mm = ['\n', self.config.text('IO', 22)]

                    if isinstance(message['fatal'], (str, unicode)):
                        mm.append(message['fatal'])

                    elif isinstance(message['fatal'], (list, tuple)):
                        mm.extend(list(message['fatal']))

                    mm.extend(self.fatal_error)
                    for m in mm:
                        if isinstance(m, (str, unicode)):
                            self.writelog(m, 0)

                    for t in self.config.threads:
                        if t.is_alive():
                            if t.thread_type in ('ttvdb', 'source'):
                                t.detail_request.put({'task': 'quit'})

                            if t.thread_type == 'cache':
                                t.cache_request.put({'task': 'quit'})

                            if t.thread_type in ('source', 'channel'):
                                t.cache_return.put('quit')

                            t.quit = True

                    self.log_queue.put('Closing down\n')
                    continue

                elif isinstance(message, (str, unicode)):
                    if message == 'Closing down\n':
                        self.quit=True

                    self.writelog(message)
                    continue

                elif isinstance(message, (list ,tuple)):
                    llevel = message[1] if len(message) > 1 else 1
                    ltarget = message[2] if len(message) > 2 else 3
                    if message[0] == None:
                        continue

                    if message[0] == 'Closing down\n':
                        self.quit = True

                    if isinstance(message[0], (str, unicode)):
                        self.writelog(message[0], llevel, ltarget)
                        continue

                    elif isinstance(message[0], (list, tuple)):
                        for m in message[0]:
                            if isinstance(m, (str, unicode)):
                                self.writelog(m, llevel, ltarget)

                        continue

                self.writelog(self.config.text('IO', 5, (message, type(message))))

            except:
                sys.stderr.write((self.now() + u'An error ocured while logging!\n').encode(self.local_encoding, 'replace'))
                traceback.print_exc()

    # end run()

    def now(self):
         return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z') + ': '

    # end now()

    def writelog(self, message, log_level = 1, log_target = 3):
        try:
            if message == None:
                return

            # If output is not yet available
            if (self.log_output == None) and (log_target & 1):
                sys.stderr.write(('Error writing to log. Not (yet) available?\n').encode(self.local_encoding, 'replace'))
                sys.stderr.write(message.encode(self.local_encoding, 'replace'))
                return

            # Log to the Frontend. To set-up later.
            if self.config.opt_dict['graphic_frontend']:
                pass

            # Log to the screen
            elif log_level == 0 or ((not self.config.opt_dict['quiet']) and (log_level & self.config.opt_dict['log_level']) and (log_target & 1)):
                sys.stderr.write(message.encode(self.local_encoding, 'replace'))

            # Log to the log-file
            if (log_level == 0 or ((log_level & self.config.opt_dict['log_level']) and (log_target & 2))) and self.log_output != None:
                if '\n' in message:
                    message = re.split('\n', message)

                    for i in range(len(message)):
                        if message[i] != '':
                            self.log_output.write(self.now() + message[i] + u'\n')
                            if self.config.opt_dict['mail_log']:
                                self.log_string.append(self.now() + message[i] + u'\n')

                else:
                    self.log_output.write(self.now() + message + u'\n')
                    if self.config.opt_dict['mail_log']:
                        self.log_string.append(self.now() + message + u'\n')

                self.log_output.flush()

        except:
            sys.stderr.write((self.now() + 'An error ocured while logging!\n').encode(self.local_encoding, 'replace'))
            traceback.print_exc()

    # end writelog()

    def send_mail(self, message, mail_address, subject=None):
        try:
            if isinstance(message, (list,tuple)):
                msg = u''.join(message)

            elif isinstance(message, (str,unicode)):
                msg = unicode(message)

            else:
                return

            if subject == None:
                subject = 'Tv_grab_nl_py %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

            msg = MIMEText(msg, _charset='utf-8')
            msg['Subject'] = subject
            msg['From'] = mail_address
            msg['To'] = mail_address
            try:
                mail = smtplib.SMTP(self.config.opt_dict['mailserver'], self.config.opt_dict['mailport'])

            except:
                sys.stderr.write(('Error mailing message: %s\n' % sys.exc_info()[1]).encode(self.local_encoding, 'replace'))
                return

            mail.sendmail(mail_address, mail_address, msg.as_string())

        except smtplib.SMTPRecipientsRefused:
            sys.stderr.write(('The mailserver at %s refused the message\n' % self.config.opt_dict['mailserver']).encode(self.local_encoding, 'replace'))

        except:
            sys.stderr.write('Error mailing message\n'.encode(self.local_encoding, 'replace'))
            sys.stderr.write(traceback.format_exc())

        mail.quit()

    # send_mail()

# end Logging

class ProgramCache(Thread):
    """
    A cache to hold program name and category info.
    TVgids and others stores the detail for each program on a separate
    URL with an (apparently unique) ID. This cache stores the fetched info
    with the ID. New fetches will use the cached info instead of doing an
    (expensive) page fetch.
    """
    def __init__(self, config, filename=None):
        Thread.__init__(self)
        """
        Create a new ProgramCache object, optionally from file
        """
        self.config = config
        self.functions = self.config.IO_func
        self.current_date = self.config.in_fetch_tz(datetime.datetime.now(pytz.utc))
        self.field_list = ['genre']
        self.field_list.extend(self.config.key_values['text'])
        self.field_list.extend(self.config.key_values['date'])
        self.field_list.extend(self.config.key_values['datetime'])
        self.field_list.extend(self.config.key_values['bool'])
        self.field_list.extend(self.config.key_values['video'])
        self.field_list.extend(self.config.key_values['int'])
        self.field_list.extend(self.config.key_values['list'])
        sqlite3.register_adapter(list, self.adapt_kw)
        sqlite3.register_converter(str('rating'), self.convert_kw)
        sqlite3.register_adapter(list, self.adapt_list)
        sqlite3.register_converter(str('listing'), self.convert_list)
        sqlite3.register_adapter(bool, self.adapt_bool)
        sqlite3.register_converter(str('boolean'), self.convert_bool)
        sqlite3.register_adapter(datetime.datetime, self.adapt_datetime)
        sqlite3.register_converter(str('datetime'), self.convert_datetime)
        sqlite3.register_adapter(datetime.date, self.adapt_date)
        sqlite3.register_converter(str('date'), self.convert_date)

        # where we store our info
        self.filename  = filename
        self.quit = False
        self.thread_type = 'cache'
        self.cache_request = Queue()
        self.config.threads.append(self)
        self.config.queues['cache'] = self.cache_request

    def offset_to_date(self, val):
        return (self.current_date + datetime.timedelta(days=val)).date()

    def date_to_offset(self, val):
        if isinstance(val, datetime.datetime):
            val = self.config.in_fetch_tz(val)
            return int(val.toordinal() - self.current_date.toordinal())

        if isinstance(val, datetime.date):
            return int(val.toordinal() - self.current_date.toordinal())

    def adapt_kw(self, val):
        ret_val = ''
        for k in val:
            ret_val += k

        return ret_val

    def convert_kw(self, val):
        ret_val = []
        for k in val:
            ret_val.append(k)

        return ret_val

    def adapt_list(self, val):
        if isinstance(val, (str, unicode)):
            return val

        if not isinstance(val, (list, tuple, set)) or len(val) == 0:
            return ''

        ret_val = ''
        for k in val:
            ret_val += ';%s' % k

        return ret_val[1:]

    def convert_list(self, val):
        ret_val = []
        val = val.split(';')
        for k in val:
            ret_val.append(k)

        return ret_val

    def adapt_bool(self, val):
        if val:
            return 'True'

        elif val == None:
            return 'None'

        else:
            return 'False'

    def convert_bool(self, val):
        if val == 'True':
            return True

        elif val == 'False':
            return False

        else:
            return None

    def adapt_datetime(self, val):
        if isinstance(val, (datetime.datetime)):
            return int(calendar.timegm(val.utctimetuple()))

        else:
            return 0

    def convert_datetime(self, val):
        try:
            if int(val) == 0 or val == '':
                return None

            if len(val) < 10:
                return datetime.date.fromordinal(int(val))

            return datetime.datetime.fromtimestamp(int(val), self.config.utc_tz)

        except:
            return None

    def adapt_date(self, val):
        if isinstance(val, (datetime.date)):
            return val.toordinal()

        return 0

    def convert_date(self, val):
        try:
            if int(val) == 0 or val == '':
                return None

            return datetime.date.fromordinal(int(val))

        except:
            return None

    def run(self):
        self.open_db()
        try:
            while True:
                if self.quit and self.cache_request.empty():
                    self.pconn.close()
                    break

                try:
                    crequest = self.cache_request.get(True, 5)

                except Empty:
                    continue

                if (not isinstance(crequest, dict)) or (not 'task' in crequest):
                    continue

                if crequest['task'] == 'query_id':
                    if not 'parent' in crequest:
                        continue

                    if self.filename == None:
                        qanswer = None

                    else:
                        for t in ('program', 'ttvdb', 'ttvdb_alias', 'tdate'):
                            if t in crequest:
                                qanswer = self.query_id(t, crequest[t])
                                break

                            else:
                                qanswer = None

                    crequest['parent'].cache_return.put(qanswer)
                    continue

                if crequest['task'] == 'query':
                    if not 'parent' in crequest:
                        continue

                    if self.filename == None:
                        qanswer = None

                    else:
                        for t in ('laststop', 'fetcheddays', 'sourceprograms', 'programdetails',
                                    'icon', 'chan_group', 'chan_scid',
                                    'ttvdb', 'ttvdb_aliasses', 'ttvdb_langs',
                                    'ep_by_id', 'ep_by_title'):
                            if t in crequest:
                                qanswer = self.query(t, crequest[t])
                                break

                            else:
                                qanswer = None

                    crequest['parent'].cache_return.put(qanswer)
                    continue

                if self.filename == None:
                    continue

                if crequest['task'] == 'add':
                    for t in ('laststop', 'fetcheddays', 'sourceprograms', 'programdetails',
                                'channelsource', 'channel', 'icon',
                                'ttvdb', 'ttvdb_alias', 'ttvdb_lang', 'episode'):
                        if t in crequest:
                            self.add(t, crequest[t])
                            continue

                if crequest['task'] == 'delete':
                    for t in ('sourceprograms', 'programdetails', 'ttvdb'):
                        if t in crequest:
                            self.delete(t, crequest[t])
                            continue

                if crequest['task'] == 'clear':
                    if 'table' in crequest:
                        for t in crequest['table']:
                            self.clear(t)

                    else:
                        self.clear('programs')
                        self.clear('credits')

                    continue

                if crequest['task'] == 'clean':
                    self.clean()
                    continue

                if crequest['task'] == 'quit':
                    self.quit = True
                    continue

        except:
            self.config.queues['log'].put({'fatal': [traceback.format_exc(), '\n'], 'name': 'ProgramCache'})
            self.ready = True
            return(98)

    def open_db(self):
        if self.filename == None:
            self.functions.log(self.config.text('IO', 6))
            return

        if os.path.isfile(self.filename +'.db'):
            # There is already a db file
            self.load_db()
            return

        elif os.path.isfile(self.filename +'.db.bak'):
            # Check for a backup
            try:
                shutil.copy(self.filename + '.db.bak', self.filename + '.db')
                self.load_db()
                return

            except:
                pass

        # Check the directory
        if not os.path.exists(os.path.dirname(self.filename)):
            try:
                os.makedirs(os.path.dirname(self.filename), 0755)
                self.load_db
                return

            except:
                self.functions.log(self.config.text('IO', 7))
                self.filename = None
                return

        self.load_db()

    def load_db(self):
        """
        Opens a sqlite cache db
        """
        # We try to open the DB,else we try the backup copy
        for try_loading in (0,1):
            try:
                self.pconn = sqlite3.connect(database=self.filename + '.db', isolation_level=None, detect_types=sqlite3.PARSE_DECLTYPES)
                self.pconn.row_factory = sqlite3.Row
                pcursor = self.pconn.cursor()
                self.functions.log(self.config.text('IO', 8))
                pcursor.execute("PRAGMA main.integrity_check")
                if pcursor.fetchone()[0] == 'ok':
                    # Making a backup copy
                    self.pconn.close()
                    if os.path.isfile(self.filename +'.db.bak'):
                        os.remove(self.filename + '.db.bak')

                    shutil.copy(self.filename + '.db', self.filename + '.db.bak')
                    self.pconn = sqlite3.connect(database=self.filename + '.db', isolation_level=None, detect_types=sqlite3.PARSE_DECLTYPES)
                    self.pconn.row_factory = sqlite3.Row
                    pcursor = self.pconn.cursor()
                    break

                if try_loading == 0:
                    # The integrity check failed. We restore a backup
                    self.functions.log([self.config.text('IO', 9, (self.filename, )), self.config.text('IO', 10)])

            except:
                if try_loading == 0:
                    # Opening the DB failed. We restore a backup
                    self.functions.log([self.config.text('IO', 9, (self.filename, )), self.config.text('IO', 10), traceback.format_exc()])

            try:
                # Just in case it is still open
                self.pconn.close()

            except:
                pass

            try:
                # Trying to restore the backup
                if os.path.isfile(self.filename +'.db'):
                    os.remove(self.filename + '.db')

                if os.path.isfile(self.filename +'.db.bak'):
                    if try_loading == 0:
                        shutil.copy(self.filename + '.db.bak', self.filename + '.db')

                    else:
                        os.remove(self.filename + '.db.bak')

            except:
                # No luck so we disable all caching related functionality
                self.functions.log([self.config.text('IO', 11, (self.filename, )), traceback.format_exc(), self.config.text('IO', 12)])
                self.filename = None
                self.config.opt_dict['disable_ttvdb'] = True
                return

        try:
            pcursor.execute("PRAGMA main.synchronous = OFF")
            pcursor.execute("PRAGMA main.temp_store = MEMORY")
            # We Check all Tables, Collumns and Indices
            for t in ('fetcheddays', 'fetcheddata',
                    'sourceprograms',  'credits',
                    'programdetails',  'creditdetails',
                    'channels', 'channelsource', 'iconsource',
                    'ttvdb', 'ttvdb_alias', 'episodes'):
                # (cid, Name, Type, Nullable = 0, Default, Pri_key index)
                pcursor.execute("PRAGMA main.table_info('%s')" % (t,))
                trows = pcursor.fetchall()
                if len(trows) == 0:
                    # Table does not exist
                    self.create_table(t)
                    continue

                else:
                    clist = {}
                    for r in trows:
                        clist[r[1].lower()] = r

                    self.check_collumns(t, clist)

                self.check_indexes(t)

            # We add if not jet there some defaults
            for a, t in self.config.ttvdb_aliasses.items():
                if not self.query_id('ttvdb_alias', {'title': t, 'alias': a}):
                    self.add('ttvdb_alias', {'title': t, 'alias': a})

        except:
            self.functions.log([self.config.text('IO', 11, (self.filename, )), traceback.format_exc(), self.config.text('IO', 12)])
            self.filename = None
            self.config.opt_dict['disable_ttvdb'] = True

    def create_table(self, table):
        print 'creating table', table
        if table == 'fetcheddays':
            create_string = u"CREATE TABLE IF NOT EXISTS %s (`sourceid` INTEGER, `channelid` TEXT, `scandate` date, `stored` boolean DEFAULT 'True'" % table
            create_string += u", PRIMARY KEY (`sourceid`, `channelid`, `scandate`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        elif table == 'fetcheddata':
            create_string = u"CREATE TABLE IF NOT EXISTS %s (`sourceid` INTEGER, `channelid` TEXT, `laststop` datetime DEFAULT NULL" % table
            create_string += u", PRIMARY KEY (`sourceid`, `channelid`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        elif table == 'sourceprograms':
            create_string = u"CREATE TABLE IF NOT EXISTS %s (`sourceid` INTEGER, `channelid` TEXT, `scandate` date" % table
            create_string += u", `genre` TEXT DEFAULT NULL"

            for key in self.config.key_values['text']:
                create_string = u"%s, `%s` TEXT DEFAULT NULL" % (create_string, key)

            for key in self.config.key_values['datetime']:
                create_string = u"%s, `%s` datetime" % (create_string, key)

            for key in self.config.key_values['date']:
                create_string = u"%s, `%s` date DEFAULT NULL" % (create_string, key)

            for key in self.config.key_values['bool']:
                create_string = u"%s, `%s` boolean DEFAULT NULL" % (create_string, key)

            for key in self.config.key_values['int']:
                create_string = u"%s, `%s` INTEGER DEFAULT NULL" % (create_string, key)

            for key in self.config.key_values['video']:
                create_string = u"%s, `%s` boolean DEFAULT NULL" % (create_string, key)

            for key in self.config.key_values['list']:
                create_string = u"%s, `%s` rating DEFAULT NULL" % (create_string, key)

            create_string += u", PRIMARY KEY (`sourceid`, `channelid`, `start-time`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        elif table == 'credits':
            create_string = u"CREATE TABLE IF NOT EXISTS %s " % table
            create_string += u"(`sourceid` INTEGER"
            create_string += u", `channelid` TEXT"
            create_string += u", `scandate` date"
            create_string += u", `prog_ID` TEXT"
            create_string += u", `start-time` datetime"
            create_string += u", `stop-time` datetime"
            create_string += u", `title` TEXT"
            create_string += u", `name` TEXT"
            create_string += u", `role` TEXT DEFAULT NULL"
            create_string += u", PRIMARY KEY (`sourceid`, `channelid`, `start-time`, `title`, `name`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        elif table == 'programdetails':
            create_string = u"CREATE TABLE IF NOT EXISTS %s (`sourceid` INTEGER, `channelid` TEXT, `prog_ID` TEXT" % table
            create_string += u", `start-time` datetime"
            create_string += u", `stop-time` datetime"
            create_string += u", `name` TEXT"
            create_string += u", `genre` TEXT DEFAULT NULL"
            for key in self.config.detail_keys['all']:
                if key in self.config.key_values['text']:
                    create_string = u"%s, `%s` TEXT DEFAULT NULL" % (create_string, key)

                if key in self.config.key_values['datetime']:
                    create_string = u"%s, `%s` datetime" % (create_string, key)

                if key in self.config.key_values['date']:
                    create_string = u"%s, `%s` date DEFAULT NULL" % (create_string, key)

                if key in self.config.key_values['bool']:
                    create_string = u"%s, `%s` boolean DEFAULT NULL" % (create_string, key)

                if key in self.config.key_values['int']:
                    create_string = u"%s, `%s` INTEGER DEFAULT NULL" % (create_string, key)

                if key in self.config.key_values['video']:
                    create_string = u"%s, `%s` boolean DEFAULT NULL" % (create_string, key)

                if key in self.config.key_values['list']:
                    create_string = u"%s, `%s` rating DEFAULT NULL" % (create_string, key)

            create_string += u", PRIMARY KEY (`sourceid`, `channelid`, `prog_ID`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        elif table == 'creditdetails':
            create_string = u"CREATE TABLE IF NOT EXISTS %s " % table
            create_string += u"(`sourceid` INTEGER"
            create_string += u", `channelid` TEXT"
            create_string += u", `prog_ID` TEXT"
            create_string += u", `start-time` datetime"
            create_string += u", `stop-time` datetime"
            create_string += u", `title` TEXT"
            create_string += u", `name` TEXT"
            create_string += u", `role` TEXT DEFAULT NULL"
            create_string += u", PRIMARY KEY (`sourceid`, `channelid`, `prog_ID`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        elif table == 'ttvdb':
            create_string = u"CREATE TABLE IF NOT EXISTS %s "  % table
            create_string += u"(`title` TEXT PRIMARY KEY ON CONFLICT REPLACE"
            create_string += u", `tid` INTEGER"
            create_string += u", `langs` listing"
            create_string += u", `tdate` date)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"


        elif table == 'ttvdb_alias':
            create_string = u"CREATE TABLE IF NOT EXISTS %s "  % table
            create_string += u"(`alias` TEXT PRIMARY KEY ON CONFLICT REPLACE"
            create_string += u", `title` TEXT)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        elif table == 'episodes':
            create_string = u"CREATE TABLE IF NOT EXISTS %s "  % table
            create_string += u"(`tid` INTEGER"
            create_string += u", `sid` INTEGER"
            create_string += u", `eid` INTEGER"
            create_string += u", `lang` TEXT DEFAULT 'nl'"
            create_string += u", `title` TEXT"
            create_string += u", `description` TEXT"
            create_string += u", `airdate` date"
            create_string += u", PRIMARY KEY (`tid`, `sid`, `eid`, `lang`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"


        elif table == 'channels':
            create_string = u"CREATE TABLE IF NOT EXISTS %s " % table
            create_string += u"(`chanid` TEXT PRIMARY KEY ON CONFLICT REPLACE"
            create_string += u", `cgroup` INTEGER DEFAULT 99"
            create_string += u", `name` TEXT)"

        elif table == 'channelsource':
            create_string = u"CREATE TABLE IF NOT EXISTS %s " % table
            create_string += u"( `chanid` TEXT"
            create_string += u", `sourceid` INTEGER"
            create_string += u", `scid` TEXT"
            create_string += u", `name` TEXT"
            create_string += u", `fgroup` TEXT DEFAULT NULL"
            create_string += u", `hd` boolean DEFAULT 'False'"
            create_string += u", `emptycount` INTEGER DEFAULT 0"
            create_string += u", PRIMARY KEY (`chanid`, `sourceid`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"


        elif table == 'iconsource':
            create_string = u"CREATE TABLE IF NOT EXISTS %s " % table
            create_string += u"(`chanid` TEXT"
            create_string += u", `sourceid` INTEGER"
            create_string += u", `icon` TEXT"
            create_string += u", PRIMARY KEY (`chanid`, `sourceid`) ON CONFLICT REPLACE)"
            if (sqlite3.sqlite_version_info >= (3, 8, 2)):
                create_string += u" WITHOUT ROWID"

        else:
            return

        with self.pconn:
            try:
                self.pconn.execute(create_string)
                #~ self.functions.log([create_string])

            except:
                self.functions.log([self.config.text('IO', 13, (table, )), traceback.format_exc(), create_string])

    def check_collumns(self, table, clist):
        def add_collumn(table, collumn):
            try:
                with self.pconn:
                    self.pconn.execute(u"ALTER TABLE %s ADD %s" % (table, collumn))
                    print 'adding collumn', collumn, 'to', table

            except:
                self.functions.log(self.config.text('IO', 14, (table, collumn)))

        def drop_table(table):
            with self.pconn:
                self.pconn.execute(u"DROP TABLE IF EXISTS %s" % (table,))

        if table == 'fetcheddays':
            for c in ('sourceid', 'channelid', 'scandate', 'stored'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

        elif table == 'fetcheddata':
            for c in ('sourceid', 'channelid'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

            if 'laststop' not in clist.keys():
                add_collumn(table, u"`laststop` datetime DEFAULT NULL")

        elif table == 'sourceprograms':
            for c in ('sourceid', 'channelid', 'scandate'):
                if c not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

            if 'genre' not in clist.keys():
                add_collumn(table, u"`genre` TEXT DEFAULT NULL")

            for c in self.config.key_values['text']:
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` TEXT DEFAULT NULL" % c)

            for c in self.config.key_values['datetime']:
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` datetime" % c)

            for c in self.config.key_values['date']:
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` date DEFAULT NULL" % c)

            for c in self.config.key_values['bool']:
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` boolean DEFAULT NULL" % c)

            for c in self.config.key_values['int']:
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` INTEGER DEFAULT NULL" % c)

            for c in self.config.key_values['video']:
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` boolean DEFAULT NULL" % c)

            for c in self.config.key_values['list']:
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` rating DEFAULT NULL" % c)

        elif table == 'credits':
            for c in ('sourceid', 'channelid', 'scandate', 'prog_ID', 'start-time', 'stop-time', 'title', 'name', 'role'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

        elif table == 'programdetails':
            for c in ('sourceid', 'channelid', 'prog_ID'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

            for c in ('start-time', 'stop-time'):
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` datetime" % c)

            for c in ('genre', 'name'):
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` TEXT DEFAULT NULL" % c)

            for c in self.config.detail_keys['all']:
                if c in self.config.key_values['text'] and c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` TEXT DEFAULT NULL" % c)

                if c in self.config.key_values['datetime'] and c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` datetime" % c)

                if c in self.config.key_values['date'] and c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` date DEFAULT NULL" % c)

                if c in self.config.key_values['bool'] and c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` boolean DEFAULT NULL" % c)

                if c in self.config.key_values['int'] and c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` INTEGER DEFAULT NULL" % c)

                if c in self.config.key_values['video'] and c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` boolean DEFAULT NULL" % c)

                if c in self.config.key_values['list'] and c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` rating DEFAULT NULL" % c)

        elif table == 'creditdetails':
            for c in ('sourceid', 'channelid', 'prog_ID', 'start-time', 'stop-time', 'title', 'name', 'role'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

        elif table == 'ttvdb':
            for c in ('title', ):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    drop_table('episodes')
                    self.create_table('episodes')
                    return

            if 'tid' not in clist.keys():
                add_collumn(table, u"`tid` INTEGER")

            if 'langs' not in clist.keys():
                add_collumn(table, u"`langs` listing")

            if 'tdate' not in clist.keys():
                add_collumn(table, u"`tdate` date")

        elif table == 'ttvdb_alias':
            for c in ('alias', ):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

            if 'title' not in clist.keys():
                add_collumn(table, u"`title` TEXT")

        elif table == 'episodes':
            for c in ('tid', 'sid', 'eid', 'lang'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

            for c in ('title', 'description'):
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` TEXT" % c)

            if 'airdate' not in clist.keys():
                add_collumn(table, u"`airdate` date")

        elif table == 'channels':
            if 'chanid' not in clist.keys():
                drop_table(table)
                self.create_table(table)
                return

            if 'cgroup' not in clist.keys():
                add_collumn(table, u"`cgroup` INTEGER DEFAULT 99")

            if 'name' not in clist.keys():
                add_collumn(table, u"`name` TEXT")

        elif table == 'channelsource':
            for c in ('chanid', 'sourceid'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

            for c in ('scid', 'name'):
                if c.lower() not in clist.keys():
                    add_collumn(table, u"`%s` TEXT" % c)

            if 'fgroup' not in clist.keys():
                add_collumn(table, u"`fgroup` TEXT DEFAULT NULL")

            if 'hd' not in clist.keys():
                add_collumn(table, u"`hd` boolean DEFAULT 'False'")

            if 'emptycount' not in clist.keys():
                add_collumn(table, u"`emptycount` INTEGER DEFAULT 0")

        elif table == 'iconsource':
            for c in ('chanid', 'sourceid'):
                if c.lower() not in clist.keys():
                    drop_table(table)
                    self.create_table(table)
                    return

            if 'icon' not in clist.keys():
                add_collumn(table, u"`icon` TEXT")

    def check_indexes(self, table):
        def add_index(table, i, clist):
            try:
                with self.pconn:
                    self.pconn.execute(u"CREATE INDEX IF NOT EXISTS '%s' ON %s %s" % (i, table, clist))

            except:
                self.functions.log(self.config.text('IO', 15, (table, i)))

        pcursor = self.pconn.cursor()
        # (id, Name, Type, Nullable = 0, Default, Pri_key index)
        pcursor.execute("PRAGMA main.index_list(%s)" % (table,))
        ilist = {}
        for r in pcursor.fetchall():
            ilist[r[1].lower()] = r

        if table == 'sourceprograms':
            if 'scandate' not in ilist:
                add_index( table, 'scandate', "('sourceid', 'channelid', 'scandate')")

            if 'progid' not in ilist:
                add_index( table, 'progid', "('sourceid', 'channelid', 'prog_ID')")

            if 'stoptime' not in ilist:
                add_index( table, 'stoptime', "('sourceid', 'channelid', 'stop-time')")

            if 'name' not in ilist:
                add_index( table, 'name', "('sourceid', 'channelid', 'name', 'episode title')")

            if 'episode' not in ilist:
                add_index( table, 'episode', "('sourceid', 'channelid', 'season', 'episode')")

        elif table == 'credits':
            if 'stoptime' not in ilist:
                add_index( table, 'stoptime', "('sourceid', 'channelid', 'stop-time')")

            if 'scandate' not in ilist:
                add_index( table, 'scandate', "('sourceid', 'channelid', 'scandate')")

            if 'progid' not in ilist:
                add_index( table, 'progid', "('sourceid', 'channelid', 'prog_ID')")

        if table == 'programdetails':
            if 'starttime' not in ilist:
                add_index( table, 'starttime', "('sourceid', 'channelid', 'start-time')")

            if 'stoptime' not in ilist:
                add_index( table, 'stoptime', "('sourceid', 'channelid', 'stop-time')")

            if 'name' not in ilist:
                add_index( table, 'name', "('sourceid', 'channelid', 'name')")

        elif table == 'creditdetails':
            if 'starttime' not in ilist:
                add_index( table, 'starttime', "('sourceid', 'channelid', 'start-time')")

            if 'stoptime' not in ilist:
                add_index( table, 'stoptime', "('sourceid', 'channelid', 'stop-time')")

        elif table == 'ttvdb':
            if 'ttvdbtid' not in ilist:
                add_index( table, 'ttvdbtid', "('tid')")

        elif table == 'episodes':
            if 'eptitle' not in ilist:
                add_index( table, 'eptitle', "('title')")

        elif table == 'channels':
            if 'cgroup' not in ilist:
                add_index( table, 'cgroup', "('cgroup')")

            if 'chan_name' not in ilist:
                add_index( table, 'chan_name', "('name')")

        elif table == 'channelsource':
            if 'scid' not in ilist:
                add_index( table, 'scid', "('sourceid', 'scid')")

            if 'fgroup' not in ilist:
                add_index( table, 'fgroup', "('sourceid', 'fgroup')")

    def query(self, table='sourceprograms', item=None):
        """
        Updates/gets/whatever.
        """
        pcursor = self.pconn.cursor()
        if table == 'fetcheddays':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys():
                return

            rval = {}
            if not "scandate" in item.keys():
                pcursor.execute(u"SELECT `scandate`, `stored` FROM fetcheddays WHERE `sourceid` = ? AND `channelid` = ?", (item['sourceid'],item['channelid']))
                for r in pcursor.fetchall():
                    offset = self.date_to_offset(r[str('scandate')])
                    rval[offset] = r[str('stored')]

                #~ print rval
                return rval

            if isinstance(item["scandate"], (datetime.date, int)):
                item["scandate"] = [item["scandate"]]

            if isinstance(item["scandate"], list):
                for sd in item["scandate"]:
                    if isinstance(sd, int):
                        offset = sd
                        sd = self.offset_to_date(sd)

                    elif isinstance(sd, datetime.date):
                        offset = self.date_to_offset(sd)

                    else:
                        continue

                    pcursor.execute(u"SELECT `stored` FROM fetcheddays WHERE `sourceid` = ? AND `channelid` = ? AND `scandate` = ?", (item['sourceid'],item['channelid'], sd))
                    r = pcursor.fetchone()
                    if r == None:
                        rval[offset] = None

                    else:
                        rval[offset] = r[str('stored')]

                #~ print rval
                return rval

        elif table == 'laststop':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys():
                return

            pcursor.execute(u"SELECT * FROM fetcheddata WHERE `sourceid` = ? AND `channelid` = ?", (item['sourceid'],item['channelid']))
            r = pcursor.fetchone()
            if r != None:
                laststop = r[str('laststop')]
                if isinstance(laststop, datetime.datetime):
                    return {'laststop': laststop}

                else:
                    return {'laststop': None}

            return None

        elif table == 'sourceprograms':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys():
                return

            programs = []
            if "scandate" in item.keys():
                if isinstance(item["scandate"], (datetime.date, int)):
                    item["scandate"] = [item["scandate"]]

                if isinstance(item["scandate"], list):
                    for sd in item["scandate"]:
                        if isinstance(sd, int):
                            offset = sd
                            sd = self.offset_to_date(sd)

                        elif not isinstance(sd, datetime.date):
                            continue

                        pcursor.execute(u"SELECT * FROM sourceprograms WHERE `sourceid` = ? AND `channelid` = ? AND `scandate` = ?", (item['sourceid'], item['channelid'], sd))
                        programs.extend(pcursor.fetchall())

            elif "start-time" in item.keys():
                if isinstance(item["start-time"], datetime.datetime):
                    item["start-time"] = [item["start-time"]]

                if isinstance(item["start-time"], list):
                    for st in item["start-time"]:
                        if not isinstance(st, datetime.datetime):
                            continue

                        pcursor.execute(u"SELECT * FROM sourceprograms WHERE `sourceid` = ? AND `channelid` = ? AND `start-time` = ?", (item['sourceid'], item['channelid'], st))
                        programs.extend(pcursor.fetchall())

            elif "range" in item.keys():
                if isinstance(item['range'], dict):
                    item['range'] = [item['range']]

                if not isinstance(item['range'], (list, tuple)) or len(item['range']) ==0:
                    return programs

                for fr in item['range']:
                    if not isinstance(fr, dict):
                        continue

                    if 'start' in fr.keys() and isinstance(fr['start'], datetime.datetime) and 'stop' in fr.keys() and  isinstance(fr['stop'], datetime.datetime):
                        pcursor.execute(u"SELECT * FROM sourceprograms WHERE `sourceid` = ? AND `channelid` = ? AND `start-time` >= ? AND `stop-time` <= ?", \
                            (item['sourceid'], item['channelid'], fr['start'], fr['stop']))
                        programs.extend(pcursor.fetchall())

                    elif 'stop' in fr.keys() and isinstance(fr['stop'], datetime.datetime):
                        pcursor.execute(u"SELECT * FROM sourceprograms WHERE `sourceid` = ? AND `channelid` = ? AND `stop-time` <= ?", \
                            (item['sourceid'], item['channelid'],fr['stop']))
                        programs.extend(pcursor.fetchall())

                    elif 'start' in fr.keys() and isinstance(fr['start'], datetime.datetime):
                        pcursor.execute(u"SELECT * FROM sourceprograms WHERE `sourceid` = ? AND `channelid` = ? AND `start-time` >= ?", \
                            (item['sourceid'], item['channelid'], fr['start']))
                        programs.extend(pcursor.fetchall())

            else:
                pcursor.execute(u"SELECT * FROM sourceprograms WHERE `sourceid` = ? AND `channelid` = ?", (item['sourceid'], item['channelid']))
                programs = pcursor.fetchall()

            programs2 = []
            for p in programs:
                pp = {}
                for key in p.keys():
                    if p[key] != None:
                        pp[unicode(key)] = p[key]

                pp['offset'] = self.date_to_offset(pp['scandate'])

                pcursor.execute(u"SELECT * FROM credits WHERE `sourceid` = ? AND `channelid` = ? AND `start-time` = ?", (item['sourceid'], item['channelid'], pp['start-time']))
                for r in pcursor.fetchall():
                    if not r[str('title')] in pp.keys():
                        pp[r[str('title')]] = []

                    if r[str('title')] in ('actor', 'guest'):
                        pp[r[str('title')]].append({'name': r[str('name')], 'role': r[str('role')]})

                    else:
                        pp[r[str('title')]].append( r[str('name')])

                programs2.append(pp)

            return programs2

        elif table == 'programdetails':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys():
                return

            programs = []
            if "prog_ID" in item.keys():
                if isinstance(item["prog_ID"], (str, unicode)):
                    item["prog_ID"] = [item["prog_ID"]]

                if isinstance(item["prog_ID"], list):
                    for sd in item["prog_ID"]:
                        if not isinstance(sd, (str, unicode)):
                            continue

                        pcursor.execute(u"SELECT * FROM programdetails WHERE `sourceid` = ? AND `channelid` = ? AND `prog_ID` = ?", \
                            (item['sourceid'], item['channelid'], sd))
                        p = pcursor.fetchone()
                        if p != None:
                            programs.append(p)

            elif "start-time" in item.keys():
                if isinstance(item["start-time"], datetime.datetime):
                    item["start-time"] = [item["start-time"]]

                if isinstance(item["start-time"], list):
                    for st in item["start-time"]:
                        if not isinstance(st, datetime.datetime):
                            continue

                        pcursor.execute(u"SELECT * FROM programdetails WHERE `sourceid` = ? AND `channelid` = ? AND `start-time` = ?", \
                            (item['sourceid'], item['channelid'], st))
                        p = pcursor.fetchone()
                        if p != None:
                            programs.append(p)

            else:
                pcursor.execute(u"SELECT * FROM programdetails WHERE `sourceid` = ? AND `channelid` = ?", (item['sourceid'], item['channelid']))
                programs = pcursor.fetchall()

            programs2 = []
            for p in programs:
                pp = {}
                for key in p.keys():
                    if p[key] != None:
                        pp[unicode(key)] = p[key]

                pcursor.execute(u"SELECT * FROM creditdetails WHERE `sourceid` = ? AND `channelid` = ? AND `prog_ID` = ?", (item['sourceid'], item['channelid'], pp['prog_ID']))
                for r in pcursor.fetchall():
                    if not r[str('title')] in pp.keys():
                        pp[r[str('title')]] = []

                    if r[str('title')] in ('actor', 'guest'):
                        pp[r[str('title')]].append({'name': r[str('name')], 'role': r[str('role')]})

                    else:
                        pp[r[str('title')]].append( r[str('name')])

                programs2.append(pp)

            return programs2

        elif table == 'ttvdb':
            pcursor.execute(u"SELECT * FROM ttvdb WHERE `tid` = ?", (item,))
            r = pcursor.fetchone()
            if r == None:
                return

            serie = {}
            serie['tid'] = r[str('tid')]
            serie['title'] = r[str('title')]
            serie['tdate'] = r[str('tdate')]
            return serie

        elif table == 'ttvdb_aliasses':
            pcursor.execute(u"SELECT `alias` FROM ttvdb_alias WHERE lower(title) = ?", (item.lower(), ))
            r = pcursor.fetchall()
            aliasses = []
            if r != None:
                for a in r:
                    aliasses.append( a[0])

            return aliasses

        elif table == 'ttvdb_langs':
            pcursor.execute(u"SELECT langs FROM ttvdb WHERE tid = ?", (item['tid'],))
            r = pcursor.fetchone()
            aliasses = []
            if r == None:
                return r[0]

            else:
                return []

        elif table == 'ep_by_id':
            qstring = u"SELECT * FROM episodes WHERE tid = ?"
            qlist = [item['tid']]
            if item['sid'] > 0:
                qstring += u" and sid = ?"
                qlist.append(item['sid'])

            if item['eid'] > 0:
                qstring += u" and eid = ?"
                qlist.append(item['eid'])

            if 'lang' in item:
                qstring += u" and lang = ?"
                qlist.append(item['lang'])

            pcursor.execute(qstring, tuple(qlist))

            r = pcursor.fetchall()
            series = []
            for s in r:
                series.append({'tid': int(s[str('tid')]),
                                          'sid': int(s[str('sid')]),
                                          'eid': int(s[str('eid')]),
                                          'title': s[str('title')],
                                          'airdate': s[str('airdate')],
                                          'lang': s[str('lang')],
                                          'description': s[str('description')]})
            return series

        elif table == 'ep_by_title':
            pcursor.execute(u"SELECT * FROM episodes WHERE tid = ? and lower(title) = ?", (item['tid'], item['title'].lower(), ))
            r = pcursor.fetchone()
            if r == None:
                return

            serie = {}
            serie['tid'] = int(r[str('tid')])
            serie['sid'] = int(r[str('sid')])
            serie['eid'] = int(r[str('eid')])
            serie['title'] = r[str('title')]
            serie['airdate'] = r[str('airdate')]
            serie['lang'] = r[str('lang')]
            serie['description'] = r[str('description')]
            return serie
        elif table == 'icon':
            if item == None:
                pcursor.execute(u"SELECT chanid, sourceid, icon FROM iconsource")
                r = pcursor.fetchall()
                icons = {}
                if r != None:
                    for g in r:
                        if not g[0] in icons:
                            icons[g[0]] ={}

                        icons[g[0]][g[1]] = g[2]

                return icons

            else:
                pcursor.execute(u"SELECT icon FROM iconsource WHERE chanid = ? and sourceid = ?", (item['chanid'], item['sourceid']))
                r = pcursor.fetchone()
                if r == None:
                    return

                return {'sourceid':  item['sourceid'], 'icon': r[0]}

        elif table == 'chan_group':
            if item == None:
                pcursor.execute(u"SELECT chanid, cgroup, name FROM channels")
                r = pcursor.fetchall()
                changroups = {}
                if r != None:
                    for g in r:
                        changroups[g[0]] = {'name': g[2],'cgroup': int(g[1])}

                return changroups

            else:
                pcursor.execute(u"SELECT cgroup, name FROM channels WHERE chanid = ?", (item['chanid'],))
                r = pcursor.fetchone()
                if r == None:
                    return

                return {'cgroup':r[0], 'name': r[1]}

        elif table == 'chan_scid':
            if item == None:
                pcursor.execute(u"SELECT chanid, sourceid, scid, name, hd FROM channelsource")
                r = pcursor.fetchall()
                scids = {}
                if r != None:
                    for g in r:
                        if not g[0] in scids:
                            scids[g[0]] ={}

                        scids[g[0]][g[1]] = {'scid': g[2],'name': g[3], 'hd': g[4]}

                return scids

            elif 'chanid' in item and 'sourceid' in item:
                pcursor.execute(u"SELECT scid FROM channelsource WHERE chanid = ? and sourceid = ?", (item['chanid'], item['sourceid']))
                r = pcursor.fetchone()
                if r == None:
                    return

                return scid

            elif 'fgroup' in item and 'sourceid' in item:
                pcursor.execute(u"SELECT scid, chanid FROM channelsource WHERE fgroup = ? and sourceid = ?", (item['fgroup'], item['sourceid']))
                r = pcursor.fetchall()
                fgroup = []
                if r != None:
                    for g in r:
                        fgroup.append({'chanid': g[1],'channelid': g[0]})

                return fgroup

            elif 'sourceid' in item:
                pcursor.execute(u"SELECT scid, chanid, name FROM channelsource WHERE sourceid = ?", (item['sourceid']))
                r = pcursor.fetchall()
                scids = {}
                if r != None:
                    for g in r:
                        if not g[0] in scids:
                            scids[g[0]] ={}

                        scids[g[0]] = {'chanid': g[1],'name': g[2]}

                return scids

    def query_id(self, table='program', item=None):
        """
        Check which ID is used
        """
        pcursor = self.pconn.cursor()
        if table == 'ttvdb':
            pcursor.execute(u"SELECT ttvdb.tid, tdate, ttvdb.title, ttvdb.langs FROM ttvdb JOIN ttvdb_alias " + \
                    "ON lower(ttvdb.title) = lower(ttvdb_alias.title) WHERE lower(alias) = ?", \
                    (item['title'].lower(), ))
            r = pcursor.fetchone()
            if r == None:
                pcursor.execute(u"SELECT tid, tdate, title, langs FROM ttvdb WHERE lower(title) = ?", (item['title'].lower(), ))
                r = pcursor.fetchone()
                if r == None:
                    return

            return {'tid': r[0], 'tdate': r[1], 'title': r[2], 'langs': r[3]}

        elif table == 'ttvdb_alias':
            pcursor.execute(u"SELECT title FROM ttvdb_alias WHERE lower(alias) = ?", (item['alias'].lower(), ))
            r = pcursor.fetchone()
            if r == None:
                if 'title' in item:
                    return False

                else:
                    return

            if 'title' in item:
                if item['title'].lower() == r[0].lower():
                    return True

                else:
                    return False

            else:
                return {'title': r[0]}

        elif table == 'tdate':
            pcursor.execute(u"SELECT tdate FROM ttvdb WHERE tid = ?", (item,))
            r = pcursor.fetchone()
            if r == None:
                return

            return r[0]

        elif table == 'chan_group':
            pcursor.execute(u"SELECT cgroup, name FROM channels WHERE chanid = ?", (item['chanid'],))
            r = pcursor.fetchone()
            if r == None:
                return

            return r[0]

    def add(self, table='sourceprograms', item=None):
        """
        Adds (or updates) a record
        """
        rec = []
        rec_upd = []
        rec2 = []
        if table == 'laststop':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys() \
              or not "laststop" in item.keys() or not isinstance(item['laststop'], datetime.datetime):
                return

            laststop = self.query(table, item)
            if laststop == None:
                add_string = u"INSERT INTO fetcheddata (`sourceid`, `channelid`, `laststop`) VALUES (?, ?, ?)"
                rec = [(item['sourceid'], item['channelid'], item['laststop'])]
                self.execute(add_string, rec)

            elif laststop['laststop'] == None or item['laststop'] > laststop['laststop']:
                add_string = u"UPDATE fetcheddata SET `laststop` = ? WHERE `sourceid` = ? AND `channelid` = ?"
                rec = [(item['laststop'], item['sourceid'], item['channelid'])]
                self.execute(add_string, rec)

        elif table == 'fetcheddays':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys() or not "scandate" in item.keys():
                return

            add_string = u"INSERT INTO fetcheddays (`sourceid`, `channelid`, `scandate`, `stored`) VALUES (?, ?, ?, ?)"
            update_string = u"UPDATE fetcheddays SET `stored` = ? WHERE `sourceid` = ? AND `channelid` = ? AND `scandate` = ?"
            sdate = self.query('fetcheddays', {'sourceid': item['sourceid'], 'channelid': item['channelid']})
            dval = True if not "stored" in item.keys() or not isinstance(item['stored'], bool) else item['stored']
            if isinstance(item["scandate"], (int, datetime.date)):
                item["scandate"] = [item["scandate"]]

            if isinstance(item["scandate"], list):
                for sd in item["scandate"]:
                    if isinstance(sd, int):
                        sd = self.offset_to_date(sd)

                    if not isinstance(sd, datetime.date):
                        continue

                    if not sd in sdate.keys() or sdate[sd] == None:
                        rec.append((item['sourceid'], item['channelid'], sd, dval))

                    elif sdate[item["scandate"]] != dval:
                        rec_upd.append((dval, item['sourceid'], item['channelid'], sd))

                self.execute(add_string, rec)
                self.execute(update_string, rec_upd)

        elif table == 'sourceprograms':
            if isinstance(item, dict):
                item = [item]

            sql_flds = u"INSERT INTO sourceprograms (`sourceid`, `channelid`, `scandate`"
            sql_cnt = u"VALUES (?, ?, ?"
            for f in self.field_list:
                sql_flds = u"%s, `%s`" % (sql_flds, f)
                sql_cnt = u"%s, ?" % (sql_cnt)

            add_string = u"%s) %s)" % (sql_flds, sql_cnt)
            add_string2 = u"INSERT INTO credits (`sourceid`, `channelid`, `scandate`, `prog_ID`, `start-time`, `title`, `name`, `role`) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            for p in item:
                if not isinstance(p, dict):
                    continue

                sql_vals = [p['sourceid'], p['channelid'], p['scandate']]
                for f in self.field_list:
                    if f in p.keys():
                        sql_vals.append(p[f])

                    else:
                        sql_vals.append(None)

                rec.append(tuple(sql_vals))
                for f in self.config.key_values['credits']:
                    if f in p.keys():
                        for cr in p[f]:
                            sql_vals = [p['sourceid'], p['channelid'], p['scandate'], p['prog_ID'], p['start-time'], f]
                            if isinstance(cr, dict):
                                sql_vals.append(cr['name'])
                                if 'role' in cr.keys():
                                    sql_vals.append(cr['role'])

                                else:
                                    sql_vals.append(None)

                            elif isinstance(cr, (str, unicode)):
                                sql_vals.append(cr)
                                sql_vals.append(None)

                            else:
                                continue

                            rec2.append(tuple(sql_vals))

            self.execute(add_string, rec)
            self.execute(add_string2, rec2)

        elif table == 'programdetails':
            if isinstance(item, dict):
                item = [item]

            sql_flds = u"INSERT INTO programdetails (`sourceid`, `channelid`, `prog_ID`, `start-time`, `stop-time`, `name`, `genre`"
            sql_cnt = u"VALUES (?, ?, ?, ?, ?, ?, ?"
            for f in self.config.detail_keys['all']:
                if f in self.field_list:
                    sql_flds = u"%s, `%s`" % (sql_flds, f)
                    sql_cnt = u"%s, ?" % (sql_cnt)

            add_string = u"%s) %s)" % (sql_flds, sql_cnt)
            add_string2 = u"INSERT INTO creditdetails (`sourceid`, `channelid`, `prog_ID`, `start-time`, `title`, `name`, `role`) VALUES (?, ?, ?, ?, ?, ?, ?)"
            for p in item:
                if not isinstance(p, dict):
                    continue

                sql_vals = [p['sourceid'], p['channelid'], p['prog_ID']]
                for f in ('start-time', 'stop-time', 'name', 'genre'):
                    if f in p.keys():
                        sql_vals.append(p[f])

                    else:
                        sql_vals.append(None)

                for f in self.config.detail_keys['all']:
                    if f in self.field_list:
                        if f in p.keys():
                            sql_vals.append(p[f])

                        else:
                            sql_vals.append(None)

                rec.append(tuple(sql_vals))
                for f in self.config.key_values['credits']:
                    if f in p.keys():
                        for cr in p[f]:
                            sql_vals = [p['sourceid'], p['channelid'], p['prog_ID'], p['start-time'], f]
                            if isinstance(cr, dict):
                                sql_vals.append(cr['name'])
                                if 'role' in cr.keys():
                                    sql_vals.append(cr['role'])

                                else:
                                    sql_vals.append(None)

                            elif isinstance(cr, (str, unicode)):
                                sql_vals.append(cr)
                                sql_vals.append(None)

                            else:
                                continue

                            rec2.append(tuple(sql_vals))

            self.execute(add_string, rec)
            self.execute(add_string2, rec2)

        elif table == 'channel':
            add_string = u"INSERT INTO channels (`chanid`, `cgroup`, `name`) VALUES (?, ?, ?)"
            update_string = u"UPDATE channels SET `cgroup` = ?, `name` = ? WHERE chanid = ?"
            if isinstance(item, dict):
                item = [item]

            if isinstance(item, list):
                g = self.query('chan_group')

                for c in item:
                    if not c['chanid'] in g.keys():
                        rec.append((c['chanid'], c['cgroup'], c['name']))

                    elif g[c['chanid']]['name'].lower() != c['name'].lower() or g[c['chanid']]['cgroup'] != c['cgroup'] \
                      or (g[c['chanid']]['cgroup'] == 10 and c['cgroup'] not in (-1, 0, 10)):
                        rec_upd.append((c['cgroup'], c['name'] , c['chanid']))

                self.execute(update_string, rec_upd)
                self.execute(add_string, rec)

        elif table == 'channelsource':
            add_string = u"INSERT INTO channelsource (`chanid`, `sourceid`, `scid`, `fgroup`, `name`, `hd`) VALUES (?, ?, ?, ?, ?, ?)"
            update_string = u"UPDATE channelsource SET `scid`= ?, `fgroup`= ?, `name`= ?, `hd`= ? WHERE `chanid` = ? and `sourceid` = ?"
            if isinstance(item, dict):
                item = [item]

            if isinstance(item, list):
                scids = self.query('chan_scid')
                for c in item:
                    if c['scid'] == '':
                        continue

                    if c['chanid'] in scids and c['sourceid'] in scids[c['chanid']]:
                        rec_upd.append((c['scid'], c['fgroup'], c['name'], c['hd'], c['chanid'], c['sourceid']))

                    else:
                        rec.append((c['chanid'], c['sourceid'], c['scid'], c['fgroup'], c['name'], c['hd']))

                self.execute(update_string, rec_upd)
                self.execute(add_string, rec)

        elif table == 'icon':
            add_string = u"INSERT INTO iconsource (`chanid`, `sourceid`, `icon`) VALUES (?, ?, ?)"
            update_string = u"UPDATE iconsource SET `icon`= ? WHERE `chanid` = ? and `sourceid` = ?"
            if isinstance(item, dict):
                item = [item]

            if isinstance(item, list):
                icons = self.query('icon')
                for ic in item:
                    if ic['chanid'] in icons and ic['sourceid'] in icons[ic['chanid']] \
                      and icons[ic['chanid']][ic['sourceid']] != ic['icon']:
                        rec_upd.append((ic['icon'], ic['chanid'], ic['sourceid']))

                    else:
                        rec.append((ic['chanid'], ic['sourceid'], ic['icon']))

                self.execute(update_string, rec_upd)
                self.execute(add_string, rec)

        elif table == 'ttvdb':
            add_string = u"INSERT INTO ttvdb (`tid`, `title`, `langs`, `tdate`) VALUES (?, ?, ?, ?)"
            rec = (int(item['tid']), item['title'], list(item['langs']), datetime.date.today())
            self.execute(add_string, rec)

        elif table == 'ttvdb_lang':
            g = self.query('ttvdb_langs', int(item['tid']))
            if len(g) == 0:
                add_string = u"INSERT INTO ttvdb (`tid`, `title`, `tdate`, `langs`) VALUES (?, ?, ?, ?)"
                rec =(int(item['tid']), item['title'], datetime.date.today(), item['lang'])
                self.execute(add_string, rec)

            else:
                langs = g[0]
                if item['lang'] not in langs:
                    langs.append(item['lang'])
                    add_string = u"UPDATE ttvdb SET langs = ?, tdate = ? WHERE tid = ?"
                    rec = (langs , datetime.date.today(), int(item['tid']))
                    self.execute(add_string, rec)

        elif table == 'ttvdb_alias':
            add_string = u"INSERT INTO ttvdb_alias (`title`, `alias`) VALUES (?, ?)"
            aliasses = self.query('ttvdb_aliasses', item['title'])
            if isinstance(item['alias'], list) and len(item['alias']) > 0:
                for a in item['alias']:
                    if not a in aliasses:
                        rec.append((item['title'], a))

                self.execute(add_string, rec)

            elif not item['alias'] in aliasses:
                rec = (item['title'], item['alias'])
                self.execute(add_string, rec)

        elif table == 'episode':
            add_string = u"INSERT INTO episodes (`tid`, `sid`, `eid`, `title`, `airdate`, `lang`, `description`) " + \
                                  u"VALUES (?, ?, ?, ?, ?, ?, ?)"
            update_string = u"UPDATE episodes SET title = ?, airdate = ?, description = ? " + \
                                       u"WHERE tid = ? and sid = ? and eid = ? and lang = ?"
            if isinstance(item, dict):
                item = [item]

            if isinstance(item, list):
                rec = []
                rec_upd = []
                for e in item:
                    ep = self.query('ep_by_id', e)
                    if ep == None or len(ep) == 0:
                        rec.append((int(e['tid']), int(e['sid']), int(e['eid']), e['title'], e['airdate'], e['lang'], e['description']))

                    elif ep[0]['title'].lower() != e['title'].lower() or ep[0]['airdate'] != e['airdate']:
                        rec_upd.append((e['title'], e['airdate'], int(e['tid']), int(e['sid']), int(e['eid']), e['lang'], e['description']))

                self.execute(update_string, rec_upd)
                self.execute(add_string, rec)

    def delete(self, table='ttvdb', item=None):
        if table == 'sourceprograms':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys():
                return

            if not "scandate" in item.keys() and not 'start-time' in item.keys():
                self.execute(u"DELETE FROM fetcheddays WHERE sourceid = ? AND channelid = ?", (item['sourceid'], item['channelid']))
                self.execute(u"DELETE FROM credits WHERE sourceid = ? AND channelid = ?", (item['sourceid'], item['channelid']))
                self.execute(u"DELETE FROM sourceprograms WHERE sourceid = ? AND channelid = ?", (item['sourceid'], item['channelid']))

            if "scandate" in item.keys():
                if isinstance(item["scandate"], (datetime.date, int)):
                    item["scandate"] = [item["scandate"]]

                if isinstance(item["scandate"], list):
                    for sd in item["scandate"]:
                        if isinstance(sd, int):
                            sd = self.offset_to_date(sd)

                        self.execute(u"DELETE FROM fetcheddays WHERE sourceid = ? AND channelid = ? AND scandate = ?", (item['sourceid'], item['channelid'], sd))
                        self.execute(u"DELETE FROM credits WHERE sourceid = ? AND channelid = ? AND scandate = ?", (item['sourceid'], item['channelid'], sd))
                        self.execute(u"DELETE FROM sourceprograms WHERE sourceid = ? AND channelid = ? AND scandate = ?", (item['sourceid'], item['channelid'], sd))

            elif "start-time" in item.keys():
                if isinstance(item["start-time"], datetime.datetime):
                    item["start-time"] = [item["start-time"]]

                if isinstance(item["start-time"], list):
                    delete_string = u"DELETE FROM credits WHERE sourceid = ? AND channelid = ? AND `start-time` = ?"
                    delete_string2 = u"DELETE FROM sourceprograms WHERE sourceid = ? AND channelid = ? AND `start-time` = ?"
                    rec = []
                    for sd in item["start-time"]:
                        if isinstance(sd, datetime.datetime):
                            rec.append((item['sourceid'], item['channelid'], sd))

                    self.execute(delete_string, rec)
                    self.execute(delete_string2, rec)

        if table == 'programdetails':
            if not isinstance(item, dict) or not "sourceid" in item.keys() or not "channelid" in item.keys():
                return

            if not "prog_ID" in item.keys() and not 'start-time' in item.keys():
                self.execute(u"DELETE FROM creditdetails WHERE sourceid = ? AND channelid = ?", (item['sourceid'], item['channelid']))
                self.execute(u"DELETE FROM programdetails WHERE sourceid = ? AND channelid = ?", (item['sourceid'], item['channelid']))

            if "prog_ID" in item.keys():
                if isinstance(item["prog_ID"], (str, unicode)):
                    item["prog_ID"] = [item["prog_ID"]]

                if isinstance(item["prog_ID"], list):
                    for sd in item["prog_ID"]:
                        if isinstance(sd, int):
                            sd = self.offset_to_date(sd)

                        self.execute(u"DELETE FROM creditdetails WHERE sourceid = ? AND channelid = ? AND prog_ID = ?", (item['sourceid'], item['channelid'], sd))
                        self.execute(u"DELETE FROM programdetails WHERE sourceid = ? AND channelid = ? AND prog_ID = ?", (item['sourceid'], item['channelid'], sd))

            elif "start-time" in item.keys():
                if isinstance(item["start-time"], datetime.datetime):
                    item["start-time"] = [item["start-time"]]

                if isinstance(item["start-time"], list):
                    delete_string = u"DELETE FROM creditdetails WHERE sourceid = ? AND channelid = ? AND `start-time` = ?"
                    delete_string2 = u"DELETE FROM programdetails WHERE sourceid = ? AND channelid = ? AND `start-time` = ?"
                    rec = []
                    for sd in item["start-time"]:
                        if isinstance(sd, datetime.datetime):
                            rec.append((item['sourceid'], item['channelid'], sd))

                    self.execute(delete_string, rec)
                    self.execute(delete_string2, rec)

        elif table == 'ttvdb':
            with self.pconn:
                self.pconn.execute(u"DELETE FROM ttvdb WHERE tid = ?",  (int(item['tid']), ))
                self.pconn.execute(u"DELETE FROM episodes WHERE tid = ?",  (int(item['tid']), ))

    def clear(self, table):
        """
        Clears the table (i.e. empties it)
        """
        self.execute(u"DROP TABLE IF EXISTS %s" % table)
        self.execute(u"VACUUM")
        self.create_table(table)
        self.check_indexes(table)

    def clean(self):
        """
        Removes all cached programming before today.
        And ttvdb ids older then 30 days
        """
        dnow = datetime.datetime.today() - datetime.timedelta(days = 1)
        dttvdb = dnow.date() - datetime.timedelta(days = 29)
        self.execute(u"DELETE FROM sourceprograms WHERE `stop-time` < ?", (dnow,))
        self.execute(u"DELETE FROM credits WHERE `stop-time` < ?", (dnow,))
        self.execute(u"DELETE FROM programdetails WHERE `stop-time` < ?", (dnow,))
        self.execute(u"DELETE FROM creditdetails WHERE `stop-time` < ?", (dnow,))
        self.execute(u"DELETE FROM fetcheddays WHERE `scandate` < ?", (dnow.date(),))
        self.execute(u"DELETE FROM ttvdb WHERE tdate < ?", (dttvdb,))

        self.execute(u"VACUUM")

    def execute(self, qstring, parameters = None):
        try:
            if parameters == None:
                with self.pconn:
                    self.pconn.execute(qstring)

            elif not isinstance(parameters, (list, tuple)) or len(parameters) == 0:
                return

            elif isinstance(parameters, tuple):
                with self.pconn:
                    self.pconn.execute(qstring, parameters)

            elif len(parameters) == 1:
                with self.pconn:
                    self.pconn.execute(qstring, parameters[0])

            elif len(parameters) > 1:
                with self.pconn:
                    self.pconn.executemany(qstring, parameters)

        except:
            self.config.log(['Database Error\n', traceback.format_exc(), qstring + '\n'])

# end ProgramCache

class InfoFiles():
    """used for gathering extra info to better the code"""
    def __init__(self, config, write_info_files = True):

        self.config = config
        self.functions = self.config.IO_func
        self.write_info_files = write_info_files
        self.info_lock = Lock()
        self.cache_return = Queue()
        self.detail_list = []
        self.raw_list = []
        self.raw_string = ''
        self.fetch_strings = {}
        self.lineup_changes = []
        self.url_failure = []
        if self.write_info_files:
            self.fetch_list = self.functions.open_file(self.config.opt_dict['xmltv_dir'] + '/fetched-programs3','w')
            self.raw_output =  self.functions.open_file(self.config.opt_dict['xmltv_dir']+'/raw_output3', 'w')

    def check_new_channels(self, source, source_channels):
        if not self.write_info_files:
            return

        if source.all_channels == {}:
            source.get_channels()

        for chan_scid, channel in source.all_channels.items():
            #~ if not (chan_scid in source_channels[source.proc_id].values() or chan_scid in empty_channels[source.proc_id]):
            if not (chan_scid in source_channels[source.proc_id].values() or chan_scid in source.empty_channels):
                self.lineup_changes.append( u'New channel on %s => %s (%s)\n' % (source.source, chan_scid, channel['name']))

        for chanid, chan_scid in source_channels[source.proc_id].items():
            #~ if not (chan_scid in source.all_channels.keys() or chan_scid in empty_channels[source.proc_id]):
            if not (chan_scid in source.all_channels.keys() or chan_scid in source.empty_channels):
                self.lineup_changes.append( u'Removed channel on %s => %s (%s)\n' % (source.source, chan_scid, chanid))

        #~ for chan_scid in empty_channels[source.proc_id]:
        for chan_scid in source.empty_channels:
            if not chan_scid in source.all_channels.keys():
                self.lineup_changes.append( u"Empty channelID %s on %s doesn't exist\n" % (chan_scid, source.source))

    def add_url_failure(self, string):
        self.url_failure.append(string)

    def addto_raw_string(self, string):
        if self.write_info_files:
            with self.info_lock:
                self.raw_string = unicode(self.raw_string + string)

    def write_raw_string(self, string):
        if self.write_info_files:
            with self.info_lock:
                self.raw_string = unicode(self.raw_string + string)
                self.raw_output.write(self.raw_string + u'\n')
                self.raw_string = ''

    def addto_raw_list(self, raw_data = None):

        if self.write_info_files:
            with self.info_lock:
                if raw_data == None:
                    self.raw_list.append(self.raw_string)
                    self.raw_string = ''
                else:
                    self.raw_list.append(raw_data)

    def write_raw_list(self, raw_data = None):

        if (not self.write_info_files) or (self.raw_output == None):
            return

        with self.info_lock:
            if raw_data != None:
                self.raw_list.append(raw_data)

            self.raw_list.sort()
            for i in self.raw_list:
                i = re.sub('\n +?\n', '\n', i)
                i = re.sub('\n+?', '\n', i)
                if i.strip() == '\n':
                    continue

                self.raw_output.write(i + u'\n')

            self.raw_list = []
            self.raw_string = ''

    def addto_detail_list(self, detail_data):

        if self.write_info_files:
            with self.info_lock:
                self.detail_list.append(detail_data)

    def write_fetch_list(self, programs, chanid = None, source = None, chan_name = '', group_slots = None):
        def value(vname):
            if vname == 'ID':
                if 'prog_ID' in tdict:
                    return tdict['prog_ID']

                return '---'

            if vname == 'from cache':
                if 'from cache' in tdict and tdict['from cache']:
                    return '*'

                return ''

            if not vname in tdict.keys():
                return '--- '

            if isinstance(tdict[vname], datetime.datetime):
                if vname == 'start-time' and 'is_gs' in tdict:
                    return u'#%s' % self.config.in_output_tz(tdict[vname]).strftime('%d %b %H:%M')

                else:
                    return self.config.in_output_tz(tdict[vname]).strftime('%d %b %H:%M')

            if isinstance(tdict[vname], bool):
                if tdict[vname]:
                    return 'True '

                return 'False '

            return tdict[vname]

        if (not self.write_info_files) or (self.fetch_list == None):
            return

        with self.info_lock:
            if isinstance(programs, tv_grab_channel.ChannelNode):

                if source in self.config.channelsource.keys():
                    sname = self.config.channelsource[source].source

                else:
                    sname = source

                fstr = u' (%3.0f/%2.0f/%2.0f) after merging from: %s\n' % \
                    (programs.program_count(), len(programs.group_slots), \
                    len(programs.program_gaps),sname)

                pnode = programs.first_node
                while isinstance(pnode, tv_grab_channel.ProgramNode):
                    fstr += u'  %s: [%s][%s] [%s:%s/%s] %s\n' % (\
                                    pnode.get_start_stop(), \
                                    pnode.get_value('ID').rjust(15), \
                                    pnode.get_value('genre')[0:10].rjust(10), \
                                    pnode.get_value('season'), \
                                    pnode.get_value('episode'), \
                                    pnode.get_value('episodecount'), \
                                    pnode.get_title())

                    if pnode.next_gap != None:
                        fstr += u'  %s: GAP\n' % pnode.next_gap.get_start_stop()

                    pnode = pnode.next

                #~ fstr += u'#\n'

            else:
                plist = deepcopy(programs)
                if group_slots != None:
                    pgs = deepcopy(group_slots)
                    fstr = u' (%3.0f/%2.0f) from: %s\n' % (len(plist), len(pgs), self.config.channelsource[source].source)
                    if len(pgs) > 0:
                        for item in pgs:
                            item['is_gs'] = True

                        plist.extend(pgs)

                else:
                    fstr = u' (%3.0f) from: %s\n' % (len(plist),  self.config.channelsource[source].source)

                plist.sort(key=lambda program: (program['start-time']))

                for tdict in plist:
                    extra = value('rerun') + value('teletext') + value('new') + value('last-chance') + value('premiere')
                    extra2 = value('HD') + value('widescreen') + value('blackwhite')

                    fstr += u'  %s%s - %s: [%s][%s] [%s:%s/%s] %s: %s\n' % (\
                                    value('from cache'), value('start-time'), value('stop-time'), \
                                    value('ID').rjust(15), value('genre')[0:10].rjust(10), \
                                    value('season'), value('episode'), value('episodecount'), \
                                    value('name'), value('episode title'))

                    #~ fstr += u'  %s-%s: [%s][%s] %s: %s [%s/%s]\n' % (\
                                    #~ self.config.output_tz.normalize(tdict['start-time'].astimezone(self.config.output_tz)).strftime('%d %b %H:%M'), \
                                    #~ self.config.output_tz.normalize(tdict['stop-time'].astimezone(self.config.output_tz)).strftime('%d %b %H:%M'), \
                                    #~ psid.rjust(15), tdict['genre'][0:10].rjust(10), \
                                    #~ tdict['name'], tdict['episode title'], \
                                    #~ tdict['season'], tdict['episode'])

            if not chanid in  self.fetch_strings:
                 self.fetch_strings[chanid] = {}
                 self.fetch_strings[chanid]['name'] = u'Channel: (%s) %s\n' % (chanid, chan_name)

            if source in self.config.channelsource.keys():
                if not source in  self.fetch_strings[chanid]:
                    self.fetch_strings[chanid][source] = fstr

                else:
                    self.fetch_strings[chanid][source] += fstr

            elif not 'channels' in self.fetch_strings[chanid]:
                self.fetch_strings[chanid]['channels'] = fstr

            else:
                self.fetch_strings[chanid]['channels'] += fstr

    def write_xmloutput(self, xml):

        if self.write_info_files:
            xml_output =self.functions.open_file(self.config.opt_dict['xmltv_dir']+'/xml_output3', 'w')
            if xml_output == None:
                return

            xml_output.write(xml)
            xml_output.close()

    def close(self, channels, combined_channels, sources):
        if not self.write_info_files:
            return

        if self.config.opt_dict['mail_info_address'] == None:
            self.config.opt_dict['mail_info_address'] = self.config.opt_dict['mail_log_address']

        if self.config.opt_dict['mail_log'] and len(self.lineup_changes) > 0:
            self.config.logging.send_mail(self.lineup_changes, self.config.opt_dict['mail_info_address'], 'Tv_grab_nl_py lineup changes')

        if self.config.opt_dict['mail_log'] and len(self.url_failure) > 0:
            self.config.logging.send_mail(self.url_failure, self.config.opt_dict['mail_info_address'], 'Tv_grab_nl_py url failures')

        if self.fetch_list != None:
            chan_list = []
            combine_list = []
            for chanid in channels.keys():
                if (channels[chanid].active or channels[chanid].is_child) and chanid in self.fetch_strings:
                    if chanid in combined_channels.keys():
                        combine_list.append(chanid)

                    else:
                        chan_list.append(chanid)

            chan_list.extend(combine_list)
            for chanid in chan_list:
                self.fetch_list.write(self.fetch_strings[chanid]['name'])
                for s in channels[chanid].merge_order:
                    if s in self.fetch_strings[chanid].keys():
                        self.fetch_list.write(self.fetch_strings[chanid][s])

                if chanid in combined_channels.keys() and 'channels' in self.fetch_strings[chanid]:
                    self.fetch_list.write(self.fetch_strings[chanid]['channels'])

            self.fetch_list.close()

        if self.raw_output != None:
            self.raw_output.close()

        if len(self.detail_list) > 0:
            f = self.functions.open_file(self.config.opt_dict['xmltv_dir']+'/detail_output3')
            if (f != None):
                f.seek(0,0)
                for byteline in f.readlines():
                    line = self.functions.get_line(f, byteline, False)
                    if line:
                        self.detail_list.append(line)

                f.close()

            f = self.functions.open_file(self.config.opt_dict['xmltv_dir']+'/detail_output3', 'w')
            if (f != None):
                ds = set(self.detail_list)
                ds = set(self.detail_list)
                tmp_list = []
                tmp_list.extend(ds)
                tmp_list.sort()
                for i in tmp_list:
                    f.write(u'%s\n' % i)

                f.close()

# end InfoFiles
