#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


"""
A simple wrapper around pickle that provides safe unpickling. In order to make
a class picklable, call C{register(cls)}.
"""


import cPickle
import cStringIO
import inspect
import sys


_safe_classes = set([
        ('__builtin__', 'set'),
        ('datetime', 'date'),
        ('datetime', 'datetime'),
        ('datetime', 'time'),
        ('datetime', 'timedelta'),
        ('logging', 'LogRecord'),
        ('psycopg2.tz', 'FixedOffsetTimezone'),
        ])


try:
    BaseException
except NameError:
    BaseException = Exception


def register(cls, _force=False):
    mod_name = cls.__module__
    cls_name = cls.__name__

    if not _force:
        try:
            __import__(mod_name)
            mod = sys.modules[mod_name]
            found_cls = getattr(mod, cls_name)
        except (ImportError, KeyError, AttributeError):
            raise cPickle.PicklingError(
                    "Can't register %r: it's not found as %s.%s" % (cls,
                        mod_name, cls_name))
        else:
            if found_cls is not cls:
                raise cPickle.PicklingError(
                        "Can't register %r: it's not the same object as %s.%s" %
                        (cls, mod_name, cls_name))

    _safe_classes.add((mod_name, cls_name))


def find_global(mod_name, cls_name):
    try:
        __import__(mod_name)
    except ImportError:
        raise cPickle.UnpicklingError(
                "Can't unpickle %s.%s: module not found or not importable" %
                (mod_name, cls_name))
    try:
        cls = getattr(sys.modules[mod_name], cls_name)
    except AttributeError:
        raise cPickle.UnpicklingError(
                "Can't unpickle %s.%s: attribute not found" %
                (mod_name, cls_name))

    if (mod_name, cls_name) in _safe_classes or _is_safe(cls):
        return cls

    raise cPickle.UnpicklingError(
            "Can't unpickle %s.%s: not in the list of safe types" %
            (mod_name, cls_name))


def _is_safe(cls):
    if not inspect.isclass(cls):
        return False

    # Assume exceptions have no side effects, because they often have
    # initializers and anyone who writes one that does have side effects
    # deserves to get rooted.
    if issubclass(cls, BaseException):
        return True

    return False


def dump(obj, stream):
    cPickle.dump(obj, stream, 2)


def dumps(obj):
    sio = cStringIO.StringIO()
    dump(obj, sio)
    return sio.getvalue()


def load(stream):
    loader = cPickle.Unpickler(stream)
    loader.find_global = find_global
    return loader.load()


def loads(data):
    sio = cStringIO.StringIO(data)
    return load(sio)
