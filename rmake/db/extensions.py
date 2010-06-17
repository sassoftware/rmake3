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


from psycopg2 import extensions as _ext
from rmake.core import types as core_types
from rmake.lib import uuid


class _Adapter(object):

    cast = None
    qstring = None

    def __init__(self, obj):
        self.obj = obj
        self.qstring = _ext.adapt(str(obj))

    def prepare(self, conn):
        if self.qstring:
            self.qstring.prepare(conn)

    def getquoted(self):
        assert self.cast
        return self.qstring.getquoted() + self.cast


class UUID_Adapter(_Adapter):
    cast = '::uuid'
_ext.register_adapter(uuid.UUID, UUID_Adapter)

def _uuid_cast(value, cursor):
    if value:
        return uuid.UUID(value)
    else:
        return None

_uuid_oids = (2950,)
_uuid_type = _ext.new_type(_uuid_oids, "UUID", _uuid_cast)


class FrozenObject_Adapter(_Adapter):
    def getquoted(self):
        return _ext.adapt(self.obj.asBuffer())
_ext.register_adapter(core_types.FrozenObject, FrozenObject_Adapter)


def register_types(db):
    _ext.register_type(_uuid_type, db._conn)
