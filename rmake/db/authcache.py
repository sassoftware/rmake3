#
# Copyright (c) 2006-2010 rPath, Inc.
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

import time
from conary.lib import sha1helper
from rmake.lib.ninamori.decorators import protected, protectedBlock


CACHE_LOCK = 0x42000001
CACHE_TIMEOUT = '15 minutes'


class AuthenticationCache(object):
    def __init__(self, db):
        self.db = db

    @protected
    def checkCache(self, tcu, checkFunc, *checkArgs):
        sessionId = self._makeSessionId(authItemList)

        tcu.execute("SELECT pg_advisory_lock(%s)", (CACHE_LOCK,))
        txn = self.db.begin()
        try:
            cu = txn.cursor()
            cu.execute("DELETE FROM auth_cache WHERE session_id = %s "
                    "RETURNING expiry >= current_timestamp AS valid",
                    (sessionId,))
            raise NotImplementedError
        except:
            txn.rollback()
            raise
        else:
            txn.commit()
        tcu.execute("SELECT pg_advisory_unlock(%s)", (CACHE_LOCK,))
