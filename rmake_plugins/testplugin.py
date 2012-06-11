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


from rmake.core import handler
from rmake.core import plug_dispatcher
from rmake.core import types
from rmake.worker import plug_worker


PREFIX = 'com.rpath.rmake.testplugin'
TEST_JOB = PREFIX
TEST_TASK_ARCCOT = PREFIX + '.arccot'
TEST_TASK_REDUCE = PREFIX + '.reduce'


class TestHandler(handler.JobHandler):
    __slots__ = ('a_result', 'b_result')
    _save = __slots__

    handler_version = 1

    jobType = TEST_JOB
    firstState = 'arccot'

    base = 10
    guard = 10
    digits = 65536

    # State: arccot -- 2 tasks do the initial number crunching.
    def arccot(self):
        finished = [0]
        def _status():
            self.setStatus(101, "Calculating arccot values {0/2;%s/2}" %
                    (finished[0],))
        _status()

        # Start a task for each arccot
        params = TestParams(self.base, self.guard, self.digits)
        a = self.newTask('arccot(5)', TEST_TASK_ARCCOT,
                ArcCotData(params, 5))
        b = self.newTask('arccot(239)', TEST_TASK_ARCCOT,
                ArcCotData(params, 239))

        # Update status immediately when one finishes
        def bb_partial(result):
            finished[0] += 1
            _status()
            return result
        self.waitForTask(a).addBoth(bb_partial)
        self.waitForTask(b).addBoth(bb_partial)

        # Collect results and move to the reduce state when both finish.
        def cb_gather(tasks):
            self.a_result = tasks[0].task_data.getObject().out
            self.b_result = tasks[1].task_data.getObject().out
            return 'reduce'
        return self.gatherTasks([a, b], cb_gather)

    # State: reduce -- combine the arccot results and format the result.
    def reduce(self):
        self.setStatus(102, "Calculating and formatting pi {1/2}")

        params = TestParams(self.base, self.guard, self.digits)
        task = self.newTask('reduce', TEST_TASK_REDUCE,
                ReduceData(params, self.a_result, self.b_result))
        def cb_gather(results):
            task, = results
            result = task.task_data.getObject().out
            self.job.data = types.FrozenObject.fromObject(result)
            self.setStatus(200, "Done! pi = %s...%s" % (result[:7],
                result[-5:]))
            return 'done'
        return self.gatherTasks([task], cb_gather)


TestParams = types.slottype('TestParams', 'base guard digits')
ArcCotData = types.slottype('ArcCotData', 'p x out')
ReduceData = types.slottype('ReduceData', 'p a b x out')


class ArcCotTask(plug_worker.TaskHandler):

    taskType = TEST_TASK_ARCCOT

    def run(self):
        data = self.getData()
        self.sendStatus(101, "Calculating arccot(%d) to %d digits" % (
            data.x, data.p.digits))

        unity = data.p.base ** (data.p.digits + data.p.guard)
        data.out = arccot(data.x, unity)

        self.setData(data)
        self.sendStatus(200, "Calculated arccot(%d)" % data.x)

        unity = data.p.base ** (data.p.digits + data.p.guard)


class ReduceTask(plug_worker.TaskHandler):

    taskType = TEST_TASK_REDUCE

    def run(self):
        data = self.getData()
        self.sendStatus(101, "Reducing pi to %d digits" % data.p.digits)

        pi = reduce_pi(data.a, data.b, data.p.base, data.p.guard)
        data.out = format_pi(pi, data.p.base, data.p.digits)

        self.setData(data)
        self.sendStatus(200, "Calculated pi")


class TestPlugin(plug_dispatcher.DispatcherPlugin, plug_worker.WorkerPlugin):

    handlerClasses = (TestHandler,)
    taskClasses = (ArcCotTask, ReduceTask)


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


def reduce_pi(a, b, base, guard):
    pi = 4 * ( (4 * a) - b)
    pi //= base ** guard
    return pi


def format_pi(pi, base, digits):
    format = {
            2: '%b',
            8: '%o',
            10: '%d',
            16: '%x',
            }.get(base)
    if not format:
        raise ValueError("Can't format base %s" % (base,))
    out = format % (pi,)
    whole = len(out) - digits
    return '.'.join((
        ''.join(out[:whole]),
        ''.join(out[whole:])))


def test_main():
    from rmake import client
    from rmake.lib import uuid
    cli = client.RmakeClient('http://localhost:9999')
    job = types.RmakeJob(uuid.uuid4(), TEST_JOB, 'nobody')
    job = cli.createJob(job.freeze(), subscribe=True)
    for event in cli.firehose.iterAll():
        ev = event.event
        if ev[:2] != ('job', str(job.job_uuid)):
            continue
        elif ev[2] == 'self':
            print event.data
            if event.data in ('finalized', 'destroyed'):
                break
        elif ev[2] == 'status':
            status = event.data
            print 'Status: %s %s' % (status.code, status.text)
            if status.detail:
                print status.detail
        else:
            print ev
        print event


if __name__ == '__main__':
    test_main()
