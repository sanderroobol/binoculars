import os
import sys
import gzip
import itertools
import random
import cPickle as pickle
import inspect
import numpy


### STATUS LINES

_status_line_length = 0
def status(line, eol=False):
    """Prints a status line to sys.stdout, overwriting the previous one.
    Set eol to True to append a newline to the end of the line"""

    global _status_line_length
    sys.stdout.write('\r{0}\r{1}'.format(' '*_status_line_length, line))
    if eol:
        sys.stdout.write('\n')
        _status_line_length = 0
    else:
        _status_line_length = len(line)

    sys.stdout.flush()

def statusnl(line):
    """Shortcut for status(..., eol=True)"""
    return status(line, eol=True)

def statuseol():
    """Starts a new status line, keeping the previous one intact"""
    global _status_line_length
    _status_line_length = 0
    sys.stdout.write('\n')
    sys.stdout.flush()

def statuscl():
    """Clears the status line, shortcut for status('')"""
    return status('')


### CONFIGURATION MANAGEMENT

def parse_range(r):
    if '-' in r:
        a, b = r.split('-')
        return range(int(a), int(b)+1)
    elif r:
        return [int(r)]
    else:
        return []

def parse_multi_range(s):
    out = []
    ranges = s.split(',')
    for r in ranges:
        out.extend(parse_range(r))
    return numpy.asarray(out)

def parse_tuple(s, length=None, type=str):
    t = tuple(type(i) for i in s.split(','))
    if length is not None and len(t) != length:
        raise ValueError('invalid tuple length: expected {0} got {0}'.format(length, len(t)))
    return t


class Config(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def copy(self):
        return self.__class__(**self.__dict__)


class ConfigurableObject(object):
    def __init__(self, config):
        if isinstance(config, Config):
            self.config = config
        else:
            self.config = Config()
            self.parse_config(config)
            for k in config:
                print 'warning: unrecognized configuration option {0} for {1}'.format(k, self.__class__.__name__)
            self.config.class_ = self.__class__

    def parse_config(self, config):
        # every known option should be pop()'ed from config, converted to a
        # proper type and stored as property in self.config, for example:
        # self.config.foo = int(config.pop('foo', 1))
        pass


class Container(object):
    def __init__(self, value=None):
        self.value = value

    def put(self, value):
        self.value = value

    def get(self):
        return self.value



### VARIOUS

def uniqid():
    return '{0:08x}'.format(random.randint(0, 2**32-1))

def grouper(iterable, n):
    while True:
        chunk = list(itertools.islice(iterable, n))
        if not chunk:
            break
        yield chunk

_python_executable = None
def register_python_executable(scriptname):
    global _python_executable
    _python_executable = sys.executable, scriptname

def get_python_executable():
    return _python_executable

def best_effort_atomic_rename(src, dest):
    if sys.platform == 'win32' and os.path.exists(dest):
        os.remove(dest)
    os.rename(src, dest)

def chunk_slicer(count, chunksize):
    """yields slice() objects that split an array of length 'count' into equal sized chunks of at most 'chunksize'"""
    chunkcount = int(numpy.ceil(float(count) / chunksize))
    realchunksize = int(numpy.ceil(float(count) / chunkcount))
    for i in range(chunkcount):
        yield slice(i*realchunksize, min(count, (i+1)*realchunksize))

def cluster_jobs(jobs, target_weight):
    jobs = sorted(jobs, key=lambda job: job.weight)

    # we cannot split jobs here, so just yield away all jobs that are overweight or just right
    while jobs and jobs[-1].weight >= target_weight:
        yield [jobs.pop()]

    while jobs:
        cluster = [jobs.pop()] # take the biggest remaining job
        size = cluster[0].weight
        for i in range(len(jobs)-1, -1, -1): # and exhaustively search for all jobs that can accompany it (biggest first)
            if size + jobs[i].weight <= target_weight:
                size += jobs[i].weight
                cluster.append(jobs.pop(i))
        yield cluster


### GZIP PICKLING (zpi)

# handle old zpi's from before ivoxoar's major restructuring
def _pickle_translate(module, name):
    if module == '__main__' and name in ('Space', 'Axis'):
        return 'ivoxoar.space', name
    return module, name

if inspect.isbuiltin(pickle.Unpickler):
    # real cPickle: cannot subclass
    def _find_global(module, name):
        module, name = _pickle_translate(module, name)
        __import__(module)
        return getattr(sys.modules[module], name)

    def pickle_load(fileobj):
        unpickler = pickle.Unpickler(fileobj)
        unpickler.find_global = _find_global
        return unpickler.load()
else:
    # pure python implementation
    class _Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            module, name = _pickle_translate(module, name)
            return pickle.Unpickler.find_class(self, module, name)

    def pickle_load(fileobj):
        unpickler = _Unpickler(fileobj)
        return unpickler.load()

def zpi_save(obj, filename):
    tmpfile = '{0}-{1}.tmp'.format(os.path.splitext(filename)[0], uniqid())
    fp = gzip.open(tmpfile, 'wb')
    try:
        try:
           pickle.dump(obj, fp, pickle.HIGHEST_PROTOCOL)
        finally:
           fp.close()
        best_effort_atomic_rename(tmpfile, filename)
    finally:
        if os.path.exists(tmpfile):
            os.remove(tmpfile)

def zpi_load(filename):
    if hasattr(filename, 'read'):
        fp = gzip.GzipFile(filename.name, fileobj=filename)
    else:
        fp = gzip.open(filename, 'rb')
    try:
        return pickle_load(fp)
    finally:
        fp.close()
