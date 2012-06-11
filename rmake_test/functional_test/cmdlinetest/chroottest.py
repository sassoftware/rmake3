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


"""
Command line chroot manipulation command tests.
"""

import errno
import re
import os
import select
import sys
import time


from conary_test import recipes
from rmake_test import rmakehelp

from conary.lib import coveragehook


def _readIfReady(fd):
    if select.select([fd], [], [], 1.0)[0]:
        return os.read(fd, 8096)
    return ''

class ChrootTest(rmakehelp.RmakeHelper):

    def testChrootManagement(self):
        self.openRmakeRepository()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)

        self.buildCfg.cleanAfterCook = False
        trv = self.addComponent('simple:source', '1-1', '',
                                [('simple.recipe', recipes.simpleRecipe)])
        jobId = self.discardOutput(helper.buildTroves, ['simple'])
        helper.waitForJob(jobId)
        chroot = helper.listChroots()[0]
        assert(chroot.path == 'simple')
        assert(chroot.jobId == jobId)
        assert(helper.client.getJob(jobId).getTrove(*chroot.troveTuple))
        path = self.rmakeCfg.getChrootDir() + '/' + chroot.path
        assert(os.path.exists(path))

        self.stopRmakeServer()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        chroot = helper.listChroots()[0]
        assert(chroot.path == 'simple')
        assert(chroot.jobId == jobId)
        assert(helper.client.getJob(jobId).getTrove(*chroot.troveTuple))

        self.captureOutput(helper.archiveChroot,'_local_', 'simple', 'foo')
        archivedPath = self.rmakeCfg.getChrootArchiveDir() + '/foo'
        assert(os.path.exists(archivedPath))
        archivedChroot = helper.listChroots()[0]
        assert(archivedChroot.path == 'archive/foo')

        self.stopRmakeServer()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)
        archivedChroot = helper.listChroots()[0]
        assert(archivedChroot.path == 'archive/foo')

        self.captureOutput(helper.deleteChroot ,'_local_', 'archive/foo')
        assert(not helper.listChroots())
        assert(not os.path.exists(archivedPath))

    def testChrootManagementMultinode(self):
        def _getChroot(helper):
            data = helper.listChroots()
            started = time.time()
            while not data:
                if time.time() - started > 60:
                    raise RuntimeError("timeout waiting for chroot to appear")
                time.sleep(.2)
                data = helper.listChroots()
            chroot, = data
            return chroot

        self.openRmakeRepository()
        client = self.startRmakeServer(multinode=True)
        helper = self.getRmakeHelper(client.uri)
        self.startNode()

        self.buildCfg.cleanAfterCook = False
        trv = self.addComponent('simple:source', '1-1', '',
                                [('simple.recipe', recipes.simpleRecipe)])
        jobId = self.discardOutput(helper.buildTroves, ['simple'])
        helper.waitForJob(jobId)
        chroot = helper.listChroots()[0]
        assert(chroot.path == 'simple')
        assert(chroot.jobId == jobId)
        self.stopNodes()
        self.startNode()
        chroot = _getChroot(helper)
        assert(chroot.path == 'simple')
        assert(chroot.jobId == jobId)


        self.stopNodes()
        self.stopRmakeServer()
        client = self.startRmakeServer(multinode=True)
        self.startNode()
        helper = self.getRmakeHelper(client.uri)

        chroot = _getChroot(helper)
        assert(chroot.path == 'simple')
        assert(chroot.jobId == jobId)

        self.captureOutput(helper.archiveChroot, self.nodeCfg.name, 'simple', 'foo')
        archivedPath = self.nodeCfg.getChrootArchiveDir() + '/foo'
        assert(os.path.exists(archivedPath))
        archivedChroot = helper.listChroots()[0]
        assert(archivedChroot.path == 'archive/foo')

        self.stopNodes()
        self.stopRmakeServer()
        client = self.startRmakeServer(multinode=True)
        helper = self.getRmakeHelper(client.uri)
        self.startNode()
        archivedChroot = _getChroot(helper)
        assert(archivedChroot.path == 'archive/foo')
        pid, master_fd = os.forkpty()
        if not pid:
            try:
                coveragehook.install()
                helper.startChrootSession(jobId, 'simple', ['/bin/sh'])
                sys.stdout.flush()
                coveragehook.save()
            finally:
                os._exit(0)
        try:
            count = 0
            data = ''
            while not data and count < 60:
                data = _readIfReady(master_fd)
                count += 1
            assert(data)
            os.write(master_fd, 'exit\n')
            data = _readIfReady(master_fd)
            while True:
                try:
                    data += _readIfReady(master_fd)
                except OSError:
                    os.waitpid(pid, 0)
                    break
        finally:
            os.close(master_fd)

    def testDeleteAllChrootsMultinode(self):
        self.openRmakeRepository()
        client = self.startRmakeServer(multinode=True)
        return
        self.startNode()
        helper = self.getRmakeHelper(client.uri)

        self.buildCfg.cleanAfterCook = False
        try:
            trv = self.addComponent('simple:source', '1-1', '',
                                    [('simple.recipe', recipes.simpleRecipe)])
            jobId = self.discardOutput(helper.buildTroves, ['simple'])
        finally:
            self.buildCfg.cleanAfterCook = True

        helper.waitForJob(jobId)
        chroot = helper.listChroots()[0]
        assert(chroot.path == 'simple')
        assert(chroot.jobId == jobId)
        assert(helper.client.getJob(jobId).getTrove(*chroot.troveTuple))
        self.captureOutput(helper.deleteAllChroots)
        assert(not helper.listChroots())

    def testChrootSession(self):
        # NOTE: This test is prone to race conditions. The chroot
        # process will occasionally quit right away, probably due to
        # a (hidden) error.
        self.openRmakeRepository()
        client = self.startRmakeServer()
        helper = self.getRmakeHelper(client.uri)


        oldStdin = sys.stdin
        self.buildCfg.cleanAfterCook = False
        self.buildCfg.configLine('[context1]')
        try:
            trv = self.addComponent('simple:source', '1-1', '',
                                    [('simple.recipe', recipes.simpleRecipe)])
            jobId = self.discardOutput(helper.buildTroves, ['simple{context1}'])
            helper.waitForJob(jobId)
        finally:
            self.buildCfg.cleanAfterCook = True

        pid, master_fd = os.forkpty()
        if not pid:
            try:
                coveragehook.install()
                helper.startChrootSession(jobId, 'simple', ['/bin/sh'])
                sys.stdout.flush()
                coveragehook.save()
            finally:
                os._exit(0)
        try:
            count = 0
            data = ''
            while not data and count < 30:
                try:
                    data = _readIfReady(master_fd)
                except OSError, err:
                    if err.errno == errno.EIO:
                        os.waitpid(pid, 0)
                        raise testsuite.SkipTestException(
                                "testChrootSession failed yet again")
                    raise
                count += 1
            assert(data)
            os.write(master_fd, 'echo "this is a test"\n')
            data = ''
            # White out bash version
            r = re.compile(r"sh-[^$]*\$")
            expected = 'echo "this is a test"\r\r\nthis is a test\r\r\nsh-X.XX$ '
            count = 0
            while not data == expected and count < 60:
                data += r.sub("sh-X.XX$", str(_readIfReady(master_fd)), 1)
                count += 1
            self.assertEquals(data, expected)
            os.write(master_fd, 'exit\n')
            data = _readIfReady(master_fd)
            while True:
                try:
                    data += _readIfReady(master_fd)
                except OSError:
                    os.waitpid(pid, 0)
                    break
            expected = 'exit\r\r\nexit\r\r\n*** Connection closed by remote host ***\r\n'
            count = 0
            while not data == expected and count < 60:
                try:
                    data += _readIfReady(master_fd)
                except OSError:
                    break
                count += 1

            self.assertEquals(data, expected)
        finally:
            os.close(master_fd)
