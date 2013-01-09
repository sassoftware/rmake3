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


import psycopg2
from psycopg2 import extensions

from rmake.lib.ninamori.connection import DatabaseConnection


class PostgresConnection(DatabaseConnection):
    __slots__ = ()
    driver = 'postgres'

    @classmethod
    def connect(cls, connectString):
        args = connectString.asDict(exclude=('driver',))
        args['database'] = args.pop('dbname')

        conn = psycopg2.connect(**args)
        conn.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        extensions.register_type(extensions.UNICODE, conn)
        return cls(conn)
