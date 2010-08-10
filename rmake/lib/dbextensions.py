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
from rmake.lib.ninamori import error as nerror


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


def adapt_FrozenObject(obj):
    return _ext.adapt(obj.asBuffer())
_ext.register_adapter(core_types.FrozenObject, adapt_FrozenObject)


def register_types(conn):
    cu = conn.cursor()
    # Look up OID for UUID type
    d = cu.query("SELECT 'pants'::regtype::oid")
    def got_oids(result):
        if not result:
            return
        oid = result[0][0]
        uuid_type = _ext.new_type((oid,), "UUID", _uuid_cast)
        _ext.register_type(uuid_type, conn._connection)
    def no_oids(reason):
        # If there isn't a UUID type, do nothing.
        reason.trap(nerror.UndefinedObjectError)
    d.addCallbacks(got_oids, no_oids)
    return d
