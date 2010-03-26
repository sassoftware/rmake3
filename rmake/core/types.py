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


from decimal import Decimal
from rmake.lib.uuid import UUID


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


class RmakeJob(_SlotCompare):
    __slots__ = ('job_uuid', 'job_type', 'owner', 'status', 'times')

    def __init__(self, job_uuid, job_type, owner, status=None, times=None):
        self.job_uuid = job_uuid
        self.job_type = job_type
        self.owner = owner
        self.status = status or JobStatus()
        self.times = times or JobTimes()


class RmakeUnit(_SlotCompare):
    __slots__ = ('unit_uuid', 'job_uuid', 'unit_type', 'node_assigned',
            'times')

    def __init__(self, unit_uuid, job_uuid, unit_type, node_assigned=None,
            status=None, times=None):
        self.unit_uuid = unit_uuid
        self.job_uuid = job_uuid
        self.unit_type = unit_type
        self.node_assigned = node_assigned
        self.status = status or JobStatus()
        self.times = times or JobTimes()


class JobStatus(_SlotCompare):
    __slots__ = ('code', 'text', 'detail')

    def __init__(self, code=0, text='', detail=None):
        self.code = code
        self.text = text
        self.detail = detail


class JobTimes(_SlotCompare):
    __slots__ = ('started', 'updated', 'finished', 'expires_after')

    def __init__(self, started=None, updated=None, finished=None,
            expires_after=None):
        self.started = started
        self.updated = updated
        self.finished = finished
        self.expires_after = expires_after
