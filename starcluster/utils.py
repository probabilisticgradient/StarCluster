# Copyright 2009-2014 Justin Riley
#
# This file is part of StarCluster.
#
# StarCluster is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# StarCluster is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with StarCluster. If not, see <http://www.gnu.org/licenses/>.

"""
Utils module for StarCluster
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import base64
import calendar
from datetime import datetime
import gzip
import inspect
import json
import os
import random
import re
import string
import sys
import time
import types
import zlib

import six
from six.moves import cStringIO as StringIO
from six.moves import cPickle

from distutils.version import LooseVersion

try:
    from urlparse import urlparse
except ImportError:
    from urllib import parse as urlparse

import iptools
import iso8601
import decorator

from starcluster import spinner
from starcluster import exception
from starcluster.logger import log


def ipy_shell(local_ns=None):
    try:
        import IPython
        if IPython.__version__ < '0.11':
            from IPython.Shell import IPShellEmbed
            return IPShellEmbed(argv=[])(local_ns)
        else:
            from IPython import embed
            return embed(user_ns=local_ns)
    except ImportError as e:
        log.error("Unable to load IPython:\n\n%s\n" % e)
        log.error("Please check that IPython is installed and working.")
        log.error("If not, you can install it via: easy_install ipython")


def set_trace():
    try:
        import pudb
        return pudb.set_trace()
    except ImportError:
        log.error("Unable to load PuDB")
        log.error("Please check that PuDB is installed and working.")
        log.error("If not, you can install it via: easy_install pudb")


class AttributeDict(dict):
    """
    Subclass of dict that allows read-only attribute-like access to
    dictionary key/values
    """
    def __getattr__(self, name):
        try:
            return self.__getitem__(name)
        except KeyError:
            return super(AttributeDict, self).__getattribute__(name)


def get_func_name(func):
    if six.PY2:
        func.func_name
    elif six.PY3:
        return func.__name__


def print_timing(msg=None, debug=False):
    """
    Decorator for printing execution time (in mins) of a function
    Optionally takes a user-friendly msg as argument. This msg will
    appear in the sentence "[msg] took XXX mins". If no msg is specified,
    msg will default to the decorated function's name. e.g:

    >>> @print_timing
    ... def myfunc():
    ...     print('Running myfunc')
    >>> myfunc()
    Running myfunc
    myfunc took 0.000 mins

    >>> @print_timing('My function')
    ... def myfunc():
    ...    print('Running myfunc')
    >>> myfunc()
    Running myfunc
    My function took 0.000 mins
    """
    prefix = msg
    if isinstance(msg, types.FunctionType):
        prefix = get_func_name(msg)

    def wrap_f(func, *arg, **kargs):
        """Raw timing function """
        time1 = time.time()
        res = func(*arg, **kargs)
        time2 = time.time()
        msg = '%s took %0.3f mins' % (prefix, (time2 - time1) / 60.0)
        if debug:
            log.debug(msg)
        else:
            log.info(msg)
        return res

    if isinstance(msg, types.FunctionType):
        return decorator.decorator(wrap_f, msg)
    else:
        return decorator.decorator(wrap_f)


def is_valid_device(dev):
    """
    Checks that dev matches the following regular expression:
    /dev/sd[a-z]$
    """
    #regex = re.compile('/dev/sd[a-z]$')
    regex = re.compile('/dev/xvdb[a-z]$')
    try:
        return regex.match(dev) is not None
    except TypeError:
        return False


def is_valid_partition(part):
    """
    Checks that part matches the following regular expression:
    /dev/sd[a-z][1-9][0-9]?$
    """
    regex = re.compile('/dev/sd[a-z][1-9][0-9]?$')
    try:
        return regex.match(part) is not None
    except TypeError:
        return False


def is_valid_bucket_name(bucket_name):
    """
    Check if bucket_name is a valid S3 bucket name (as defined by the AWS
    docs):

    1. 3 <= len(bucket_name) <= 255
    2. all chars one of: a-z 0-9 .  _ -
    3. first char one of: a-z 0-9
    4. name must not be a valid ip
    """
    regex = re.compile('[a-z0-9][a-z0-9\._-]{2,254}$')
    if not regex.match(bucket_name):
        return False
    if iptools.ipv4.validate_ip(bucket_name):
        return False
    return True


def is_valid_image_name(image_name):
    """
    Check if image_name is a valid AWS image name (as defined by the AWS docs)

    1. 3<= len(image_name) <=128
    2. all chars one of: a-z A-Z 0-9 ( ) . - / _
    """
    regex = re.compile('[\w\(\)\.\-\/_]{3,128}$')
    try:
        return regex.match(image_name) is not None
    except TypeError:
        return False


def is_valid_hostname(hostname):
    """From StackOverflow on 2013-10-04:

    http://stackoverflow.com
    /questions/2532053/validate-a-hostname-string#answer-2532344
    """
    if len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1]  # strip exactly one dot from the right
    allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))


def make_one_liner(script):
    """
    Returns command to execute python script as a one-line python program

    e.g.

        import os
        script = '''
        import os
        print(os.path.exists('hi'))
        '''
        os.system(make_one_liner(script))

    Will print out:

        <module 'os' from ...>
        False
    """
    return 'python -c "%s"' % script.strip().replace('\n', ';')


def is_url(url):
    """
    Returns True if the provided string is a valid url
    """
    try:
        parts = urlparse(url)
        scheme = parts[0]
        netloc = parts[1]
        if scheme and netloc:
            return True
        else:
            return False
    except:
        return False


def is_iso_time(iso):
    """
    Returns True if provided time can be parsed in iso format
    to a datetime tuple
    """
    try:
        iso_to_datetime_tuple(iso)
        return True
    except iso8601.ParseError:
        return False


def iso_to_datetime_tuple(iso):
    """
    Converts an iso time string to a datetime tuple
    """
    return iso8601.parse_date(iso)


def get_utc_now(iso=False):
    """
    Returns datetime.utcnow with UTC timezone info
    """
    now = datetime.utcnow().replace(tzinfo=iso8601.iso8601.UTC)
    if iso:
        return datetime_tuple_to_iso(now)
    else:
        return now


def datetime_tuple_to_iso(tup):
    """
    Converts a datetime tuple to a UTC iso time string
    """
    iso = datetime.strftime(tup.astimezone(iso8601.iso8601.UTC),
                            "%Y-%m-%dT%H:%M:%S.%fZ")
    return iso


def get_elapsed_time(past_time):
    ptime = iso_to_localtime_tuple(past_time)
    now = datetime.now()
    delta = now - ptime
    timestr = time.strftime("%H:%M:%S", time.gmtime(delta.seconds))
    if delta.days != -1:
        timestr = "%d days, %s" % (delta.days, timestr)
    return timestr


def iso_to_unix_time(iso):
    dtup = iso_to_datetime_tuple(iso)
    secs = calendar.timegm(dtup.timetuple())
    return secs


def iso_to_javascript_timestamp(iso):
    """
    Convert dates to Javascript timestamps (number of milliseconds since
    January 1st 1970 UTC)
    """
    secs = iso_to_unix_time(iso)
    return secs * 1000


def iso_to_localtime_tuple(iso):
    secs = iso_to_unix_time(iso)
    t = time.mktime(time.localtime(secs))
    return datetime.fromtimestamp(t)


def permute(a):
    """
    Returns generator of all permutations of a

    The following code is an in-place permutation of a given list, implemented
    as a generator. Since it only returns references to the list, the list
    should not be modified outside the generator. The solution is
    non-recursive, so uses low memory. Work well also with multiple copies of
    elements in the input list.

    Retrieved from:
        http://stackoverflow.com/questions/104420/ \
        how-to-generate-all-permutations-of-a-list-in-python
    """
    a.sort()
    yield list(a)
    if len(a) <= 1:
        return
    first = 0
    last = len(a)
    while 1:
        i = last - 1
        while 1:
            i = i - 1
            if a[i] < a[i + 1]:
                j = last - 1
                while not (a[i] < a[j]):
                    j = j - 1
                # swap the values
                a[i], a[j] = a[j], a[i]
                r = a[i + 1:last]
                r.reverse()
                a[i + 1:last] = r
                yield list(a)
                break
            if i == first:
                a.reverse()
                return


def has_required(programs):
    """
    Same as check_required but returns False if not all commands exist
    """
    try:
        return check_required(programs)
    except exception.CommandNotFound:
        return False


def check_required(programs):
    """
    Checks that all commands in the programs list exist. Returns
    True if all commands exist and raises exception.CommandNotFound if not.
    """
    for prog in programs:
        if not which(prog):
            raise exception.CommandNotFound(prog)
    return True


def which(program):
    """
    Returns the path to the program provided it exists and
    is on the system's PATH

    retrieved from code snippet by Jay:

    http://stackoverflow.com/questions/377017/ \
    test-if-executable-exists-in-python
    """
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file


def tailf(filename):
    """
    Constantly displays the last lines in filename
    Similar to 'tail -f' unix command
    """
    # Set the filename and open the file
    file = open(filename, 'r')

    # Find the size of the file and move to the end
    st_results = os.stat(filename)
    st_size = st_results[6]
    file.seek(st_size)

    while True:
        where = file.tell()
        line = file.readline()
        if not line:
            time.sleep(1)
            file.seek(where)
            continue
        print(line, end="") # already has newline


def v2fhelper(v, suff, version, weight):
    parts = v.split(suff)
    if 2 != len(parts):
        return v
    version[4] = weight
    version[5] = parts[1]
    return parts[0]


def program_version_greater(ver1, ver2):
    """
    Return True if ver1 > ver2 using semantics of comparing version
    numbers
    """
    return LooseVersion(ver1) > LooseVersion(ver2)


def test_version_to_float():
    assert program_version_greater("1", "0.9")
    assert program_version_greater("0.0.0.2", "0.0.0.1")
    assert program_version_greater("1.0", "0.9")
    assert program_version_greater("2.0.1", "2.0.0")
    assert program_version_greater("2.0.1", "2.0")
    assert program_version_greater("2.0.1", "2")
    assert program_version_greater("0.9.1", "0.9.0")
    assert program_version_greater("0.9.2", "0.9.1")
    assert program_version_greater("0.9.11", "0.9.2")
    assert program_version_greater("0.9.12", "0.9.11")
    assert program_version_greater("0.10", "0.9")
    assert program_version_greater("2.0", "2.0b35")
    assert program_version_greater("1.10.3", "1.10.3b3")
    assert program_version_greater("88", "88a12")
    assert program_version_greater("0.0.33", "0.0.33rc23")
    assert program_version_greater("0.91.2", "0.91.1")
    assert program_version_greater("0.9999", "0.91.1")
    assert program_version_greater("0.9999", "0.92")
    assert program_version_greater("0.91.10", "0.91.1")
    assert program_version_greater("0.92", "0.91.11")
    assert program_version_greater("0.92", "0.92b1")
    assert program_version_greater("0.9999", "0.92b3")
    print("All tests passed")


def get_arg_spec(func, debug=True):
    """
    Convenience wrapper around inspect.getargspec

    Returns a tuple whose first element is a list containing the names of all
    required arguments and whose second element is a list containing the names
    of all keyword (optional) arguments.
    """
    allargs, varargs, keywords, defaults = inspect.getargspec(func)
    if 'self' in allargs:
        allargs.remove('self')  # ignore self
    nargs = len(allargs)
    ndefaults = 0
    if defaults:
        ndefaults = len(defaults)
    nrequired = nargs - ndefaults
    args = allargs[:nrequired]
    kwargs = allargs[nrequired:]
    if debug:
        log.debug('nargs = %s' % nargs)
        log.debug('ndefaults = %s' % ndefaults)
        log.debug('nrequired = %s' % nrequired)
        log.debug('args = %s' % args)
        log.debug('kwargs = %s' % kwargs)
        log.debug('defaults = %s' % str(defaults))
    return args, kwargs


def chunk_list(ls, items=8):
    """
    iterate through 'chunks' of a list. final chunk consists of remaining
    elements if items does not divide len(ls) evenly.

    items - size of 'chunks'
    """
    itms = []
    for i, v in enumerate(ls):
        if i >= items and i % items == 0:
            yield itms
            itms = [v]
        else:
            itms.append(v)
    if itms:
        yield itms


def generate_passwd(length):
    return "".join(random.sample(string.letters + string.digits, length))


class struct_group(tuple):
    """
    grp.struct_group: Results from getgr*() routines.

    This object may be accessed either as a tuple of
      (gr_name,gr_passwd,gr_gid,gr_mem)
    or via the object attributes as named in the above tuple.
    """

    attrs = ['gr_name', 'gr_passwd', 'gr_gid', 'gr_mem']

    def __new__(cls, grp):
        if type(grp) not in (list, str, tuple):
            grp = (grp.name, grp.password, int(grp.GID),
                   [member for member in grp.members])
        if len(grp) != 4:
            raise TypeError('expecting a 4-sequence (%d-sequence given)' %
                            len(grp))
        return tuple.__new__(cls, grp)

    def __getattr__(self, attr):
        try:
            return self[self.attrs.index(attr)]
        except ValueError:
            raise AttributeError


class struct_passwd(tuple):
    """
    pwd.struct_passwd: Results from getpw*() routines.

    This object may be accessed either as a tuple of
      (pw_name,pw_passwd,pw_uid,pw_gid,pw_gecos,pw_dir,pw_shell)
    or via the object attributes as named in the above tuple.
    """

    attrs = ['pw_name', 'pw_passwd', 'pw_uid', 'pw_gid', 'pw_gecos',
             'pw_dir', 'pw_shell']

    def __new__(cls, pwd):
        if type(pwd) not in (list, str, tuple):
            pwd = (pwd.loginName, pwd.password, int(pwd.UID), int(pwd.GID),
                   pwd.GECOS, pwd.home, pwd.shell)
        if len(pwd) != 7:
            raise TypeError('expecting a 4-sequence (%d-sequence given)' %
                            len(pwd))
        return tuple.__new__(cls, pwd)

    def __getattr__(self, attr):
        try:
            return self[self.attrs.index(attr)]
        except ValueError:
            raise AttributeError


def join(data, with_str):
    if six.PY3:
        str_data = []
        for x in data:
            if isinstance(x, bytes):
                x = x.decode('utf-8')
            str_data.append(x)
    return with_str.join(data)


def gzip_compress(data):
    if six.PY2:
        s = StringIO()
        gfile = gzip.GzipFile(fileobj=s, mode='w')
        gfile.write(data)
        gfile.close()
        s.seek(0)
        return s.read()
    else:
        return gzip.compress(bytes(data, 'latin-1'))


def gzip_decompress(data):
    if six.PY2:
        zfile = StringIO(data)
        gfile = gzip.GzipFile(fileobj=zfile, mode='r')
        data = gfile.read()
        gfile.close()
        return data
    else:
        return gzip.decompress(data)


def dump_compress_encode(obj, use_json=False, chunk_size=None):
    serializer = cPickle
    if use_json:
        serializer = json
    if six.PY2:
        compressed = zlib.compress(serializer.dumps(obj))
        p = base64.b64encode(compressed)
    if six.PY3:
        data = serializer.dumps(obj)
        if isinstance(data, str):
            data = bytes(data, 'ascii')
        compressed = zlib.compress(data)
        p = base64.b64encode(compressed).decode('ascii')
    if chunk_size is not None:
        p = [p[i:i + chunk_size] for i in range(0, len(p), chunk_size)]
    return p


def decode_uncompress_load(string, use_json=False):
    string = join(string, '')
    serializer = cPickle
    if use_json:
        serializer = json
    data = zlib.decompress(base64.b64decode(string))
    if isinstance(data, bytes):
        try:
            data = data.decode('utf-8')
        except UnicodeDecodeError:
            try:
                cPickle.loads(data)
                # is was a pickle; everything's going to be okay
            except Exception as err:
                print(err)
                print("Raw string: %s" % string)
                print("Data: %s" % data)
    return serializer.loads(data)


def is_unicode(data):
    if six.PY2:
        return isinstance(data, unicode)
    if six.PY3:
        return isinstance(data, str)


def is_str_or_unicode(data):
    if six.PY2:
        return isinstance(data, (str, unicode))
    if six.PY3:
        return isinstance(data, str)


def startswith(data, str):
    if six.PY2:
        return data.startswith(str)
    if six.PY3:
        if isinstance(data, bytes):
            return data.startswith(bytes(str, 'utf-8'))
        elif isinstance(data, str):
            return data.startswith(str)


def to_str(data):
    # you don't want to use str() on bytes; you'll get nonsense in Python 3
    if isinstance(data, bytes):
        return data.decode('utf-8')
    if six.PY2:
        data = str(data)
    elif six.PY3 and hasattr(data, '__str__'):
        data = data.__str__()
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    return data


def iteritems(data):
    if six.PY2:
        return data.iteritems()
    elif six.PY3:
        return data.items()


def string_to_file(string, filename):
    s = StringIO(string)
    s.name = filename
    return s


def strings_to_files(strings, fname_prefix=''):
    fileobjs = [StringIO(s) for s in strings]
    if fname_prefix:
        fname_prefix += '_'
    for i, f in enumerate(fileobjs):
        f.name = '%s%d' % (fname_prefix, i)
    return fileobjs


def get_fq_class_name(obj):
    return '.'.join([obj.__module__, obj.__class__.__name__])


def size_in_kb(obj):
    return sys.getsizeof(obj) / 1024.


def get_spinner(msg):
    """
    Logs a status msg, starts a spinner, and returns the spinner object.
    This is useful for long running processes:

    s = get_spinner("Long running process running...")
    try:
        (do something)
    finally:
        s.stop()
    """
    s = spinner.Spinner()
    log.info(msg, extra=dict(__nonewline__=True))
    s.start()
    return s
