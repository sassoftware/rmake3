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
