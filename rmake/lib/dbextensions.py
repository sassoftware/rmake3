#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from psycopg2 import extensions as _ext
from rmake.core import types as core_types
from rmake.lib import uuid
from rmake.lib import logger
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
    d = cu.query("SELECT 'uuid'::regtype::oid")
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
    d.addErrback(logger.logFailure)
    return d
