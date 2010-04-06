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
from rmake.lib import uuid


class UUID_Adapter(object):
    def __init__(self, uuid):
        self._uuid = uuid

    def prepare(self, conn):
        pass

    def getquoted(self):
        return "'%s'::uuid" % self._uuid
_ext.register_adapter(uuid.UUID, UUID_Adapter)

def _uuid_cast(value, cursor):
    if value:
        return uuid.UUID(value)
    else:
        return None

_uuid_oids = (2950,)
_uuid_type = _ext.new_type(_uuid_oids, "UUID", _uuid_cast)


def register_types(db):
    _ext.register_type(_uuid_type, db._conn)
