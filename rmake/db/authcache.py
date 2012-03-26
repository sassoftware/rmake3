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


import time

from conary.lib import sha1helper
from conary.dbstore.sqlerrors import DatabaseLocked, ColumnNotUnique


CACHE_TIMEOUT = 15 * 60 # timeout after 15 mins

class AuthenticationCache(object):
    def __init__(self, db):
        self.db = db

    def cache(self, authItemList):
        sessionId =  self._makeSessionId(authItemList)
        timeStamp = time.time() + CACHE_TIMEOUT
        cu = self.db.cursor()
        for x in range(3):
            try:
                cu.execute("DELETE FROM AuthCache WHERE sessionId = ?",
                        cu.binary(sessionId))
                cu.execute("INSERT INTO AuthCache (sessionid, timestamp) "
                        "VALUES (?, ?)", cu.binary(sessionId), timeStamp)
            except (DatabaseLocked, ColumnNotUnique):
                # Race condition -- someone inserted a conflicting value
                # between our statements. Try again.
                continue
            else:
                # Success
                break
        else:
            raise
        self._deleteOld(cu)
        self.db.commit()

    def _deleteOld(self, cu):
        cu.execute('DELETE FROM AuthCache WHERE timeStamp < ?', time.time())

    def resetCache(self):
        cu = self.db.cursor()
        cu.execute('DELETE FROM AuthCache')
        self.db.commit()

    def _makeSessionId(self, authItemList):
        return sha1helper.sha1String('\0'.join([str(x) for x in authItemList]))

    def checkCache(self, authItemList):
        cu = self.db.cursor()
        sessionId = self._makeSessionId(authItemList)
        self._deleteOld(cu)
        match = False
        result = cu.execute('SELECT timeStamp FROM AuthCache WHERE sessionId=?',
                cu.binary(sessionId))
        if result.fetchall():
            match = True
            cu.execute('UPDATE AuthCache SET timeStamp=? WHERE sessionId=?',
                    time.time() + CACHE_TIMEOUT, cu.binary(sessionId))
        self.db.commit()
        return match
