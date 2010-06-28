#
# Copyright (c) 2010 rPath, Inc.
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

from twisted.internet import defer

from rmake.core import handler
from rmake.core import plug_dispatcher
from rmake.worker import plug_worker


class TestPlugin(plug_dispatcher.DispatcherPlugin, plug_worker.WorkerPlugin):

    def dispatcher_pre_setup(self, dispatcher):
        handler.registerHandler(TestHandler)

    def worker_get_task_types(self):
        return { 'test': TestTask }


class TestHandler(handler.JobHandler):
    handler_version = 1

    jobType = 'test'
    firstState = 'beta'

    # State: alpha -- start one task and wait for completion
    def alpha(self):
        self.setStatus(101, 'Running task alpha {0/2;0/1}')
        task = self.newTask('alpha 1', 'test', None)
        d = self.waitForTask(task)
        def cb_finished(new_task):
            if new_task.status.failed:
                self.setStatus(400, new_task.status.text,
                        new_task.status.detail)
                return 'done'
            else:
                # Move to next state
                return 'beta'
        d.addCallback(cb_finished)
        d.addErrback(self.failJob)
        return d

    # State: beta -- start three tasks and wait for completion
    def beta(self):
        total = 4
        finished = [0]
        def _status():
            self.setStatus(102, 'Running task beta {1/2;%s/%s}' % (finished[0],
                total))

        dfrs = []
        for x in range(total):
            task = self.newTask('beta %s' % x, 'test', None)
            d = self.waitForTask(task)
            def cb_finished(new_task):
                finished[0] += 1
                _status()
                return new_task
            d.addCallback(cb_finished)
            dfrs.append(d)

        all = defer.DeferredList(dfrs)
        def cb_all_finished(results):
            failed = [x for x in results if x[0] is defer.FAILURE]
            if failed:
                self.failJob(failed[0][1])

            tasks = [x[1] for x in results if x[0] is defer.SUCCESS]
            failed = [x for x in tasks if x.status.failed]
            if failed:
                detail = ''.join('%s: %s: %s\n%s\n\n' % (
                    x.task_name, x.status.code, x.status.text, x.status.detail)
                    for x in failed)
                self.setStatus(400, 'Job failed: %s subtasks failed' %
                        len(failed), detail)
            else:
                self.setStatus(200, 'Job complete {2/2}')
            return 'done'
        all.addCallback(cb_all_finished)
        return all


class TestTask(plug_worker.TaskHandler):

    digits = 16384

    def run(self):
        self.sendStatus(101, "Calculating pi to %s digits" % self.digits)
        res = pi(self.digits)
        self.sendStatus(200, "pi = %s..." % str(res)[:8])


def arccot(x, unity):
    sum = xpower = unity // x
    n = 3
    sign = -1
    while 1:
        xpower //= x * x
        term = xpower // n
        if not term:
            break
        sum += sign * term
        sign = -sign
        n += 2
    return sum


def pi(digits):
    unity = 10 ** (digits + 10)
    pi = 4 * (4 * arccot(5, unity) - arccot(239, unity))
    return pi // 10**10
