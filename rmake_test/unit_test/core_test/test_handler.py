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


from testutils import mock
from twisted.python import failure as tw_failure
from twisted.trial import unittest

from rmake.core import handler as rmk_handler
from rmake.core import types
from rmake.lib import logger
from rmake.lib import uuid


class DispatcherTest(unittest.TestCase):

    def setUp(self):
        self.job = types.RmakeJob(
                uuid.uuid4(), 'test', 'spam', data='ham').freeze()
        self.postponedErrors = []

    def tearDown(self):
        mock.unmockAll()

    def _postponeError(self, failure=None, rethrow=True):
        """Stuffs the present exception into postponedErrors so they can be
        rethrown in a context where trial will see them.

        If C{rethrow} is C{True} (the default), also reraise the exception in
        the current context. Since postponing errors is mainly useful for
        smuggling tracebacks out of contexts that catch and log all errors,
        rethrowing is normally good since it tests the error handling.
        """
        if failure is None:
            failure = tw_failure.Failure()
        self.postponedErrors.append(failure)
        if rethrow:
            failure.raiseException()

    def _raisePostponed(self):
        """Throw the first previously postponed exception, if there was one."""
        if self.postponedErrors:
            self.postponedErrors[0].raiseException()

    def test_callbacks(self):
        """Test monitoring a task using deferreds and callbacks."""
        mock.mock(logger, 'logFailure')
        disp = mock.MockObject()
        handler = rmk_handler.JobHandler(disp, self.job, None)
        task = handler.newTask('spam', 'ham', 'eggs').freeze()

        toSend = [
                types.JobStatus(100, 'one'),
                types.JobStatus(150, 'two'),
                types.JobStatus(200, 'three'),
                ]
        expected = toSend[:]
        def watch_func(task, somearg):
            try:
                assert somearg == 'pants'
                assert task.status == expected.pop(0)
            except:
                self._postponeError()
        handler.watchTask(task, watch_func, somearg='pants')

        # First callback raises an exception
        d1 = handler.waitForTask(task)
        def blow_up(result):
            raise RuntimeError("oops.")
        d1.addBoth(blow_up)

        # Second one should still get the original result
        d2 = handler.waitForTask(task)
        success = []
        def works_ok(result):
            assert result.status == toSend[-1]
            success.append(1)
        d2.addCallback(works_ok)
        d2.addErrback(self._postponeError)

        for status in toSend:
            task2 = task.thaw()
            task2.status = status
            handler.taskUpdated(task2)

        # Everything above should have been called synchronously, but just to
        # make sure, we've touched "success" once the last callback fires.
        assert success
        self._raisePostponed()
