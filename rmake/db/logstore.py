#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

from conary.lib import sha1helper
from conary.lib import util
from conary.repository import datastore

class DeletableDataStore(datastore.DataStore):
    def deleteFile(self, hash):
        path = self.hashToPath(hash)
        util.removeIfExists(path)

class LogStore(object):
    def __init__(self, path):
        util.mkdirChain(path)
        self.store = DeletableDataStore(path)

    def getTrovePath(self, trove):
        return self.store.hashToPath(self.hashTrove(trove))

    def hashTrove(self, trove):
        return sha1helper.sha1ToString(
                sha1helper.sha1String('%s %s=%s[%s]' % (trove.jobId,
                      trove.getName(), trove.getVersion(), trove.getFlavor())))

    def hashTroveInfo(self, jobId, name, version, flavor):
        return sha1helper.sha1ToString(
                sha1helper.sha1String('%s %s=%s[%s]' % (jobId, name, version, flavor)))

    def addTroveLog(self, trove):
        hash = self.hashTrove(trove)
        self.store.addFile(open(trove.logPath, 'r'), hash, integrityCheck=False)
        trove.logPath = ''

    def hasTroveLog(self, trove):
        hash = self.hashTrove(trove)
        return self.store.hasFile(hash)

    def openTroveLog(self, trove):
        hash = self.hashTrove(trove)
        return self.store.openFile(hash)

    def deleteLogs(self, troveInfoList):
        hashes = [ self.hashTroveInfo(*x) for x in troveInfoList ]
        for hash in hashes:
            self.store.deleteFile(hash)
