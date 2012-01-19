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
