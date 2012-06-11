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


import os
import stat
import time

from conary.lib import util
from conary import versions
from rmake.worker.chroot import rootmanager
from rmake.lib import logfile

from rmake_test import rmakehelp


class ChrootManagerTest(rmakehelp.RmakeHelper):

    def testQueue(self):
        root = self.cfg.root
        root0 = root + '/foo'
        root1 = root + '/foo-1'
        root2 = root + '/foo-2'
        root3 = root + '/foo-3'

        queue = rootmanager.ChrootQueue(root, 2) # limit of two chroots
        self.assertEquals(queue.requestSlot('foo', [], True),
                          (None, root0))
        self.assertEquals(queue.requestSlot('foo', [], True),
                          (None, root1))
        self.assertEquals(queue.requestSlot('foo', [], True), None)


        util.mkdirChain(root0)
        queue.chrootFinished(root0)
        self.assertEquals(sorted(queue.listOldChroots()), [root0])
        self.assertEquals(queue.requestSlot('foo', [], True), (root0, root2))
        util.mkdirChain(root2)
        util.rmtree(root0)
        queue.deleteChroot(root0)
        self.assertEquals(queue.requestSlot('foo', [], True), None)

        queue.markBadChroot(root2)
        # we can't reuse root2 anymore - it's marked as bad.  But that means 
        # it's no longer using a space, so we can add a chroot
        self.assertEquals(queue.requestSlot('foo', [], True), (None, root0))
        self.assertEquals(queue.requestSlot('foo', [], True), None)

        def _shorten(x):
            return x[len(root)+1:]
        self.assertEquals(sorted(queue.listChroots()), [_shorten(x) for x in (root0, root1)])
        self.assertEquals(sorted(queue.listOldChroots()), [])

    def testGetBestOldChrootNoReuse(self):
        # If we're not reusing chroots, get the oldest one available.
        root = self.cfg.root
        root0 = root + '/foo'
        root1 = root + '/foo-1'
        root2 = root + '/foo-2'
        root3 = root + '/foo-3'
        osStatResults = {}

        idx = 0
        for dir in root3, root2, root0, root1:
            util.mkdirChain(dir)
            time.sleep(.1)
            osStatResults[dir] = idx
            idx += 1
        oldStat = os.stat
        queue = rootmanager.ChrootQueue(root, 2) # limit of two chroots
        try:
            def _newStat(x):
                class _mockResult(object):
                    def __init__(self, result, mtime):
                        self.result = result
                        self.mtime = mtime

                    def __getitem__(self, key):
                        if key == stat.ST_MTIME:
                            return self.mtime
                        return self.result[key]
                    def __getattr__(self, key):
                        return getattr(self.result, key)

                result = oldStat(x)
                if x in osStatResults:
                    result = _mockResult(result, osStatResults[x])
                return result
            os.stat = _newStat

            for dir in root3, root2, root0, root1:
                self.assertEquals(queue._getBestOldChroot([], False), dir)
                util.rmtree(dir)
        finally:
            os.stat = oldStat

    def testGetBestOldChrootReuse(self):
        # If we are reusing chroots, look at the components installed 
        # in the databases.
        root = self.cfg.root
        make = self.makeTroveTuple
        queue = rootmanager.ChrootQueue(root, 2) # limit of two chroots
        queue2 = rootmanager.ChrootQueue(root, 5) # limit of three chroots

        root0 = root + '/foo'
        root1 = root + '/foo-1'
        db0 = self.openDatabase(root0)
        db1 = self.openDatabase(root1)
        for db, flavor in (db0, 'is: x86'), (db1, 'is:x86_64'):
            self.addDbComponent(db, 'foo:runtime', ':1', flavor)
            self.addDbComponent(db, 'bar:runtime', ':1', flavor)
            self.addDbComponent(db, 'bam:runtime', ':1', flavor)
        self.addDbComponent(db0, 'baz:runtime', ':1', 'is:x86')

        buildReqs = [make('foo:runtime', ':1/2-1-1', 'is:x86')]
        self.assertEquals(queue._getBestOldChroot(buildReqs, True), root0)
        self.assertEquals(queue2.requestSlot('trvName', buildReqs, True)[0],
                          None)
        queue2.reset()

        buildReqs += [make('bar:runtime', ':1/2-1-1', 'is:x86')]
        self.assertEquals(queue2.requestSlot('trvName', buildReqs, True)[0],
                          root0)
        # but now root0 is retaken (even though it hasn't been moved yet)
        # make sure that it doesn't show up twice in the "ok" list!
        self.assertEquals(queue2.requestSlot('trvName', buildReqs, True)[0],
                          None)
        queue2.reset()

        buildReqs = [make('foo:runtime', ':1/2-1-1', 'is:x86_64')]
        self.assertEquals(queue._getBestOldChroot(buildReqs, True), root1)
        self.assertEquals(queue2.requestSlot('trvName', buildReqs, True)[0],
                          None)
        queue2.reset()
        buildReqs += [make('bar:runtime', ':1/2-1-1', 'is:x86_64')]
        self.assertEquals(queue2.requestSlot('trvName', buildReqs, True)[0],
                          root1)

        # add extra stuff that doesn't match.  This will make the second
        # root be a better match because it has less stuff
        # 2*(1 match) - 2 wrong = -2, x86_64 one has 1 wrong = -1 
        self.addDbComponent(db0, 'ffff:runtime', ':1', 'is:x86')
        self.addDbComponent(db0, 'bzah:runtime', ':1', 'is:x86')

        buildReqs = [ make('foo:runtime', ':1/2-1-1', 'is:x86') ]
        self.assertEquals(queue._getBestOldChroot(buildReqs, True), root1)

        queue2.reset()
        self.assertEquals(queue2.requestSlot('trvName', buildReqs, True)[0],
                          None)

    def testFakeChroot(self):
        groupRecipe = """
class SimpleGroup(GroupRecipe):
    name = 'group-foo'
    version = '1'
    clearBuildReqs()
    def setup(r):
        r.add('foo:lib')
"""
        trv = self.addComponent('group-foo:source=1',
                                 [('group-foo.recipe', groupRecipe)])
        self.addComponent('foo:lib')
        mgr = rootmanager.ChrootManager(self.rmakeCfg)
        trv = self.newBuildTrove(1, *trv.getNameVersionFlavor())
        factory = mgr.getRootFactory(self.buildCfg, [], [], [], trv)
        factory.create()
        logFile = logfile.LogFile(self.workDir + '/rmake.out')
        logFile.redirectOutput()
        chroot = factory.start()
        try:
            chroot.buildTrove(self.buildCfg, versions.Label('localhost@rpl:branch'),
                              *trv.getNameVersionFlavor())
            results = chroot.checkResults(wait=30, *trv.getNameVersionFlavor())
            assert(results.isBuildSuccess())
        finally:
            chroot.stop()
        factory.clean()
        assert(factory.root != '/tmp/rmake')
        assert(not os.path.exists('/tmp/rmake/builds/group-foo'))
