#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import copy
import inspect
import sys
from rmake.lib import chutney
from rmake.lib import uuid
from rmake.lib.ninamori.types import namedtuple

from twisted.python import reflect

NAMESPACE_TASK = uuid.UUID('14dfcf54-40e4-11df-b434-33d2b616adec')

IMMUTABLE_TYPES = (int, long, basestring, uuid.UUID, tuple, frozenset)


def freezify(cls, frameCount=1):
    """Returns a 'frozen' namedtuple type of the given SlotCompare subclass."""
    assert issubclass(cls, SlotCompare)
    frozenName = 'Frozen' + cls.__name__

    # namedtuple constructs the base class.
    baseType = namedtuple(frozenName, cls.__slots__)

    # Subclass the namedtuple to add a thaw() mixin and to copy read-only
    # versions of the thawed class' properties.
    frozenDict = {'__slots__': (), '_thawedType': cls}
    for name, value in inspect.getmembers(cls):
        if isinstance(value, property):
            frozenDict[name] = property(value.fget)
    frozenType = type(frozenName, (baseType, _Thawable), frozenDict)

    # Stash forward and backward type references.
    cls._frozenType = frozenType
    frozenType._thawedType = cls

    # Frozen types are always safe to unpickle.
    module = sys._getframe(frameCount).f_globals.get('__name__', '__main__')
    frozenType.__module__ = module
    chutney.register(frozenType, _force=True)

    return frozenType


class SlotCompare(object):
    """Base class for types that can be easily compared using their slots.

    Types can also be freezified to make them freezable to a namedtuple form.
    """
    __slots__ = ()
    _frozenType = None

    def __init__(self, *args, **kwargs):
        for n, name in enumerate(self.__slots__):
            if n < len(args):
                value = args[n]
            else:
                value = kwargs.get(name, None)
            setattr(self, name, value)

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        for slot in self.__slots__:
            if getattr(self, slot) != getattr(other, slot):
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __copy__(self):
        cls = type(self)
        new = cls.__new__(cls)
        for name in self.__slots__:
            setattr(new, name, getattr(self, name))
        return new

    def __deepcopy__(self, memo):
        cls = type(self)
        new = cls.__new__(cls)
        for name in self.__slots__:
            setattr(new, name, copy.deepcopy(getattr(self, name), memo))
        return new

    def freeze(self):
        if not self._frozenType:
            raise TypeError("Object of type %s cannot be frozen" %
                    reflect.qual(type(self)))
        vals = {}
        for name in self.__slots__:
            value = getattr(self, name)
            if value is None or isinstance(value, IMMUTABLE_TYPES):
                vals[name] = value
            elif isinstance(value, SlotCompare):
                vals[name] = value.freeze()
            else:
                raise TypeError("Can't freeze field %r of type %r as it is "
                        "not a type known to be immutable" % (name,
                            type(value).__name__))
        return self._frozenType(**vals)

    def thaw(self):
        return self


class _Thawable(object):
    """Mixin class used by freezify to add thawing support to named tuples."""
    __slots__ = ()

    def freeze(self):
        return self

    def thaw(self):
        ret = object.__new__(self._thawedType)
        for name, value in zip(self._fields, self):
            if isinstance(value, _Thawable):
                value = value.thaw()
            setattr(ret, name, value)
        return ret


def slottype(name, attrs):
    attrs = attrs.replace(',', ' ').split()
    module = sys._getframe(1).f_globals.get('__name__', '__main__')
    cls = type(name, (SlotCompare,), {
        '__slots__': attrs,
        '__module__': module,
        })
    chutney.register(cls, _force=True)
    return cls


class RmakeJob(SlotCompare):
    __slots__ = ('job_uuid', 'job_type', 'owner', 'status', 'times', 'data')

    def __init__(self, job_uuid, job_type, owner, status=None, times=None,
            data=None):
        self.job_uuid = job_uuid
        self.job_type = job_type
        self.owner = owner
        self.status = status or JobStatus()
        self.times = times or JobTimes()
        self.data = data


FrozenRmakeJob = freezify(RmakeJob)


class RmakeTask(SlotCompare):
    __slots__ = ('task_uuid', 'job_uuid', 'task_name', 'task_type',
            'task_zone', 'task_data', 'node_assigned', 'status', 'times',
            )

    def __init__(self, task_uuid, job_uuid, task_name, task_type,
            task_data=None, node_assigned=None, status=None, times=None,
            task_zone=None):
        if not task_uuid:
            task_uuid = uuid.uuid5(NAMESPACE_TASK,
                    str(job_uuid) + str(task_name))
        self.task_uuid = task_uuid
        self.job_uuid = job_uuid
        self.task_name = task_name
        self.task_type = task_type
        self.task_zone = task_zone
        self.task_data = task_data
        self.node_assigned = node_assigned
        self.status = status or JobStatus()
        self.times = times or JobTimes()


FrozenRmakeTask = freezify(RmakeTask)


class JobStatus(SlotCompare):
    __slots__ = ('code', 'text', 'detail')

    def __init__(self, code=0, text='', detail=None):
        self.code = code
        self.text = text
        self.detail = detail

    @property
    def completed(self):
        return 200 <= self.code < 300

    @property
    def failed(self):
        return 400 <= self.code < 600

    @property
    def final(self):
        return self.completed or self.failed

    @classmethod
    def from_failure(cls, reason, text="Fatal error", code=400):
        text = "%s: %s: %s" % (text,
                reflect.qual(reason.type),
                reflect.safe_str(reason.value))
        return cls(code, text, reason.getTraceback())


FrozenJobStatus = freezify(JobStatus)


class JobTimes(SlotCompare):
    __slots__ = ('started', 'updated', 'finished', 'expires_after', 'ticks')

    TICK_OVERRIDE = 1000000

    def __init__(self, started=None, updated=None, finished=None,
            expires_after=None, ticks=-1):
        self.started = started
        self.updated = updated
        self.finished = finished
        self.expires_after = expires_after
        self.ticks = ticks


FrozenJobTimes = freezify(JobTimes)


class TaskCapability(namedtuple('TaskCapability', 'taskType')):
    """Worker is capable of running the given task type."""
chutney.register(TaskCapability)


class ZoneCapability(namedtuple('ZoneCapability', 'zoneName')):
    """Worker participates in the given zone."""
chutney.register(ZoneCapability)


class ThawedObject(namedtuple('ThawedObject', 'object')):
    """Encapsulated object, which can be frozen into a FrozenObject."""

    # Thawed API

    @classmethod
    def fromObject(cls, obj):
        return cls(obj)

    def getObject(self):
        return self.object

    # Frozen API

    def asBuffer(self):
        return self.freeze().asBuffer()

    # Translation API

    def freeze(self):
        return FrozenObject.fromObject(self.object)

    def thaw(self):
        return self

chutney.register(ThawedObject)


class FrozenObject(namedtuple('FrozenObject', 'data')):
    """Encapsulated pickled object."""

    # Thawed API

    @classmethod
    def fromObject(cls, obj):
        return cls('pickle:' + chutney.dumps(obj))

    def getObject(self):
        return self._thaw()

    def _thaw(self):
        idx = self.data.index(':')
        kind = self.data[:idx]
        if kind == 'pickle':
            return chutney.loads(self.data[idx+1:])
        else:
            raise RuntimeError("Unrecognized serialization format %s" % kind)

    # Frozen API

    def asBuffer(self):
        return buffer(self.data)

    # Translation API

    def freeze(self):
        return self

    def thaw(self):
        return ThawedObject(self._thaw())

    def __deepcopy__(self, memo=None):
        return self
    __copy__ = __deepcopy__

chutney.register(FrozenObject)
