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


from rmake.build import buildjob
from rmake.worker import chroot
from rmake.worker import node

from rmake.lib.apiutils import thaw, freeze


def toBuildFlavors(frz):
    if '\\000' in frz or '\0' in frz:
        # Looks like the old marshal-based format, just ignore it
        return []
    else:
        return [ thaw('flavor', x) for x in frz.splitlines() ]


def fromBuildFlavors(flavorList):
    return '\n'.join([freeze('flavor', x) for x in flavorList])


class NodeStore(object):
    def __init__(self, db):
        self.db = db

    def addNode(self, name, host, slots, flavors):
        cu = self.db.cursor()
        cu.execute("""DELETE FROM Nodes where nodeName=?""", name)
        cu.execute("""INSERT INTO Nodes (nodeName, host, slots, buildFlavors,
                      active) 
                      VALUES (?, ?, ?, ?, 1)""",
                       name, host, slots, fromBuildFlavors(flavors))

    def removeNode(self, name):
        cu = self.db.cursor()
        cu.execute("""UPDATE Nodes SET active=0 WHERE nodeName=?""", name)

    def deactivateAllNodes(self):
        cu = self.db.cursor()
        cu.execute("""UPDATE Nodes SET active=0""")
        cu.execute("""UPDATE Chroots SET active=0""")

    def setChrootsForNode(self, nodeName, chrootPaths):
        cu = self.db.cursor()
        cu.execute("SELECT chrootId, troveId, path"
                   " FROM Chroots WHERE nodeName=?", nodeName)
        chrootList = cu.fetchall()
        currentPaths = set(chrootPaths)
        knownPaths = set(x[2] for x in chrootList)
        extraPaths = knownPaths - currentPaths
        newPaths = currentPaths - knownPaths
        extraIds = [ (x[0],x[1]) for x in chrootList if x[2] in extraPaths ]

        for chrootId, troveId in extraIds:
            cu.execute("""DELETE FROM Chroots WHERE chrootId=?""",
                          chrootId)
            # use troveId too so we don't have to add an index on chrootId
            cu.execute("""UPDATE BuildTroves set chrootId=0 WHERE troveId=?
                          AND chrootId=?""", troveId, chrootId)
        for path in newPaths:
            self._createChrootId(cu, nodeName, path, None)

    def getNodes(self, names):
        cu = self.db.cursor()
        nodes = []
        for name in names:
            cu.execute('''SELECT nodeName, host, slots, buildFlavors, active 
                          FROM Nodes WHERE name=?''', name)
            results = self._fetchOne(cu, name)
            name, host, slots, buildFlavors, active = results
            buildFlavors = toBuildFlavors(buildFlavors)
            chroots = self.getChrootsForHost(name)
            nodes.append(node.Node(name, host, slots, buildFlavors, chroots,
                                   active))
        return nodes

    def listNodes(self):
        nodes = []
        cu = self.db.cursor()
        cu.execute('''SELECT nodeName, host, slots, buildFlavors, active 
                      FROM Nodes where active=1''')
        for name, host, slots, buildFlavors, active in cu.fetchall():
            buildFlavors = toBuildFlavors(buildFlavors)
            chroots = self.getChrootsForHost(name)
            nodes.append(node.Node(name, host, slots, buildFlavors, active,
                                   chroots))
        return nodes

    def getEmptySlots(self):
        """
            Return the number of slots that are currently not in use.

            This should be the number of jobs that can be added at the moment
            w/o using up all of the available slots.
        """
        totalSlots = self.getSlotCount()
        cu = self.db.cursor()
        cu.execute("SELECT COUNT(*) FROM Jobs WHERE state in (?, ?)",
                   buildjob.JOB_STATE_BUILD, buildjob.JOB_STATE_STARTED)
        currentJobs = cu.fetchone()[0]
        if totalSlots < currentJobs:
            return 0
        cu.execute("""SELECT jobId,COUNT(jobId) FROM Chroots
                      JOIN Nodes USING(nodeName)
                      LEFT JOIN BuildTroves
                            ON (Chroots.troveId=BuildTroves.troveId)
                      LEFT JOIN Jobs USING(jobId)
                      WHERE Chroots.active=1
                        AND Nodes.active=1
                        AND jobId IS NOT NULL
                      GROUP BY jobId""")
        jobsSeen = 0
        slots = 0
        for jobId, count in cu:
            jobsSeen += 1
            slots += count
        totalUsed = slots + (currentJobs - jobsSeen)
        return max(totalSlots - totalUsed, 0)

    def getSlotCount(self):
        cu = self.db.cursor()
        totalSlots = cu.execute(
                        """SELECT SUM(slots)
                           FROM Nodes WHERE active=1""").fetchone()[0]
        return max(totalSlots, 1)


    def getOrCreateChrootId(self, trove):
        cu = self.db.cursor()
        chrootId = cu.execute("""SELECT chrootId from Chroots
                                  WHERE nodeName=? and path=?""",
                              trove.chrootHost,
                              trove.chrootPath).fetchall()
        if not chrootId:
            return self.createChrootId(trove)
        return chrootId[0][0]

    def createChrootId(self, trove):
        cu = self.db.cursor()
        host = trove.getChrootHost()
        path = trove.getChrootPath()
        troveId = self.db.jobStore._getTroveId(cu, trove.jobId, 
                                             *trove.getNameVersionFlavor(True))
        return self._createChrootId(cu, host, path, troveId)

    def _createChrootId(self, cu, nodeName, path, troveId):
        cu.execute("""INSERT INTO Chroots (nodeName, path, troveId, active) 
                      VALUES (?,?,?,0)""", nodeName, path, troveId)
        chrootId = cu.lastrowid
        return chrootId

    def moveChroot(self, nodeName, path, newPath):
        cu = self.db.cursor()
        cu.execute("""UPDATE Chroots SET path=? WHERE nodeName=? AND path=?""",
                      newPath, nodeName, path)

    def removeChroot(self, nodeName, path):
        cu = self.db.cursor()
        cu.execute("""SELECT chrootId From Chroots
                        WHERE nodeName=? AND path=?""", nodeName, path)
        chrootId = self.db._getOne(cu, (nodeName, path))[0]
        cu.execute("""DELETE FROM Chroots WHERE chrootId=?""", chrootId)
        cu.execute("""UPDATE BuildTroves set chrootId=0 WHERE chrootId=?""",
                    chrootId)

    def chrootIsActive(self, nodeName, path):
        cu = self.db.cursor()
        cu.execute('SELECT active From Chroots WHERE nodeName=? AND path=?',
                    nodeName, path)
        active = self.db._getOne(cu, (nodeName, path))[0]
        return bool(active)

    def setChrootActive(self, trove, active=True):
        cu = self.db.cursor()
        host = trove.getChrootHost()
        path = trove.getChrootPath()
        if not (host and path):
            return
        cu.execute("""UPDATE Chroots SET active=? WHERE nodeName=? and path=?""",
                    int(active), host, path)
        return

    def getChrootsForHost(self, nodeName):
        cu = self.db.cursor()
        cu.execute("""SELECT Chroots.nodeName, path,
                             jobId, troveName, version, flavor, Chroots.active
                       FROM Chroots
                       LEFT JOIN BuildTroves USING(troveId)
                       LEFT JOIN Nodes ON(Chroots.nodeName = Nodes.nodeName)
                       WHERE Nodes.active=1 and Nodes.nodeName=?""", nodeName)
        return self._getChroots(cu)


    def getAllChroots(self):
        cu = self.db.cursor()
        cu.execute("""SELECT Chroots.nodeName, path,
                             jobId, troveName, version, flavor, Chroots.active
                       FROM Chroots
                       LEFT JOIN BuildTroves USING(troveId)
                       LEFT JOIN Nodes ON(Chroots.nodeName = Nodes.nodeName)
                       WHERE Nodes.active=1""")
        return self._getChroots(cu)

    def _getChroots(self, cu):
        chroots = []
        for nodeName, path, jobId, name, version, flavor, active in cu:
            if jobId:
                version = thaw('version', version)
                flavor = thaw('flavor', flavor)
                troveTuple = (name, version, flavor)
            else:
                troveTuple = None
            c = chroot.Chroot(nodeName, path, jobId, troveTuple, active)
            chroots.append(c)
        return chroots
