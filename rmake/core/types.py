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
import cPickle
from rmake.lib import uuid
from rmake.lib.ninamori.types import namedtuple

NAMESPACE_TASK = uuid.UUID('14dfcf54-40e4-11df-b434-33d2b616adec')


class _SlotCompare(object):
    __slots__ = ()

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


class RmakeJob(_SlotCompare):
    __slots__ = ('job_uuid', 'job_type', 'owner', 'status', 'times', 'data')

    def __init__(self, job_uuid, job_type, owner, status=None, times=None,
            data=None):
        self.job_uuid = job_uuid
        self.job_type = job_type
        self.owner = owner
        self.status = status or JobStatus()
        self.times = times or JobTimes()
        self.data = data


class RmakeTask(_SlotCompare):
    __slots__ = ('task_uuid', 'job_uuid', 'task_name', 'task_type',
            'task_data', 'node_assigned', 'status', 'times')

    def __init__(self, task_uuid, job_uuid, task_name, task_type,
            task_data=None, node_assigned=None, status=None, times=None):
        if not task_uuid:
            task_uuid = uuid.uuid5(NAMESPACE_TASK,
                    str(job_uuid) + str(task_name))
        self.task_uuid = task_uuid
        self.job_uuid = job_uuid
        self.task_name = task_name
        self.task_type = task_type
        self.task_data = task_data
        self.node_assigned = node_assigned
        self.status = status or JobStatus()
        self.times = times or JobTimes()


class JobStatus(_SlotCompare):
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
        return 400 <= self.code < 500

    @property
    def final(self):
        return self.completed or self.failed


class JobTimes(_SlotCompare):
    __slots__ = ('started', 'updated', 'finished', 'expires_after', 'ticks')

    def __init__(self, started=None, updated=None, finished=None,
            expires_after=None, ticks=-1):
        self.started = started
        self.updated = updated
        self.finished = finished
        self.expires_after = expires_after
        self.ticks = ticks


class TaskCapability(namedtuple('TaskCapability', 'taskType')):
    pass


class FrozenObject(_SlotCompare):
    """Encapsulated pickled object."""
    __slots__ = ('data',)

    def __init__(self, data):
        self.data = data

    @classmethod
    def fromObject(cls, obj):
        return cls('pickle:' + cPickle.dumps(obj, 2))

    def freeze(self):
        return self.data

    def thaw(self):
        idx = self.data.index(':')
        kind = self.data[:idx]
        if kind == 'pickle':
            return cPickle.loads(self.data[idx+1:])
        else:
            raise RuntimeError("Unrecognized serialization format %s" % kind)
