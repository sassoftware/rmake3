#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import time

from conary.lib import sha1helper

CACHE_TIMEOUT = 15 * 60 # timeout after 15 mins

class AuthenticationCache(object):
    def __init__(self, db):
        self.db = db

    def cache(self, authItemList):
        sessionId =  self._makeSessionId(authItemList)
        cu = self.db.cursor()
        timeStamp = time.time() + CACHE_TIMEOUT
        cu.execute('INSERT INTO AuthCache VALUES (?, ?)', sessionId, timeStamp)
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
                            sessionId)
        if result.fetchall():
            match = True
            cu.execute('UPDATE AuthCache SET timeStamp=? WHERE sessionId=?',
                        time.time() + CACHE_TIMEOUT, sessionId)
        self.db.commit()
        return match
