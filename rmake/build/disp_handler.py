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
Job handler used by the dispatcher to run trove build jobs.
"""

import logging
from twisted.internet import defer

from rmake import failure
from rmake.build import buildjob
from rmake.build import constants as buildconst
from rmake.build import dephandler
from rmake.build.publisher import JobStatusPublisher
from rmake.core import handler
from rmake.core import types

log = logging.getLogger(__name__)


class BuildHandler(handler.JobHandler):

    jobType = buildconst.BUILD_JOB
    firstState = 'load_troves'

    def setup(self):
        self.build_plugin = self.dispatcher.plugins.getPlugin('build')
        self.cfg = self.build_plugin.cfg
        self.dh = None
        self.build_pending = None

    def load_troves(self):
        job = self.getData()

        for cfg in job.iterConfigList():
            cfg.repositoryMap.update(self.cfg.getRepositoryMap())
            cfg.user.extend(self.cfg.reposUser)
            cfg.reposName = self.cfg.reposName

        for troveTup in job.getMainConfig().primaryTroves:
            job.getTrove(*troveTup).setPrimaryTrove()

        # Start a load trove task
        loadTroves = job.troves.values()
        self.setStatus(buildjob.JOB_STATE_LOADING,
                'Loading %d troves' % len(loadTroves))
        task = self.newTask('load', buildconst.LOAD_TASK, job)

        d = self.waitForTask(task)
        def cb_loaded(task):
            if task.status.failed:
                self.setStatus(400, task.status.text, task.status.detail)
                return 'done'
            return self._finish_load(task.task_data.thaw())
        d.addCallback(cb_loaded)
        return d

    def _finish_load(self, job):
        publisher = JobStatusPublisher()
        job.setPublisher(publisher)
        self.buildJob = job

        troves = sorted(job.iterTroves())
        normalTroves = [x for x in troves
                if not x.isRedirectRecipe() and not x.isFilesetRecipe()]
        if normalTroves:
            # Cannot build redirect or fileset troves with other troves, and it
            # was probably unintentional from recursing a group, so just remove
            # them.  Other cases, such as mixing only different solitary
            # troves, will error out later on sanity check, and that's OK.
            # (RMK-991)
            troves = normalTroves
        job.setBuildTroves(troves)

        # TODO: match prebuilt troves
        assert not job.getMainConfig().jobContext

        # TODO: proper per-job logging
        joblog = logging.getLogger('dephandler.' + self.job.job_uuid.short)
        self.dh = dephandler.DependencyHandler(publisher, joblog, troves)

        # TODO: sanity check

        self.setData(job)
        return 'build'

    def build(self):
        self.setStatus(101, "Building troves")
        self.build_pending = defer.Deferred()
        self._do_loop()
        return self.build_pending

    def _do_loop(self):
        """Try to move the build job forward without blocking."""
        if not self.dh.moreToDo():
            return self._finish_build()
        did_something = False

        while True:
            resolveJob = self.dh.getNextResolveJob()
            if not resolveJob:
                break
            self._do_resolve(resolveJob)
            did_something = True

        while self.dh.hasBuildableTroves():
            self._do_build()
            did_something = True

    def _do_resolve(self, resolveJob):
        """Start the process of resolving one trove."""
        trv = resolveJob.getTrove()
        trv.troveQueued("Ready for dependency resolution")

        task = self.newTask('resolve %s' % trv.getTroveString(),
                buildconst.RESOLVE_TASK, resolveJob)

        d = self.waitForTask(task)
        def cb_done(task):
            if task.status.failed:
                fail = failure.InternalError(task.status.text,
                        task.status.detail or '')
                trv.troveFailed(fail)
            else:
                trv.troveResolved(task.task_data.thaw())
            self.clock.callLater(0, self._do_loop)
        d.addCallback(cb_done)
        d.addErrback(self.failJob, message="Internal error resolving trove:")

    def _do_build(self):
        trv, (buildReqs, crossReqs) = self.dh.popBuildableTrove()
        trv.troveQueued("Waiting to be assigned to chroot")

        job = TroveBuildJob(trv, buildReqs, crossReqs)
        job.targetLabel = trv.cfg.getTargetLabel(trv.getVersion())
        if trv.isDelayed():
            job.builtTroves = self.buildJob.getBuiltTroveList()
        else:
            job.builtTroves = []

        task = self.newTask('build ' + trv.getTroveString(),
                buildconst.BUILD_TASK, job)

        d = self.waitForTask(task)
        def cb_done(task):
            if task.status.failed:
                fail = failure.InternalError(task.status.text,
                        task.status.detail or '')
                trv.troveFailed(fail)
            else:
                upd = task.task_data.thaw().trove
                if upd.isFailed():
                    trv.troveFailed(upd.getFailureReason())
                elif upd.isBuilt():
                    trv.troveBuilt(upd.builtTroves)
                else:
                    trv._setState(upd.state, upd.status)
            self.clock.callLater(0, self._do_loop)
        d.addCallback(cb_done)
        d.addErrback(self.failJob, message="Internal error building trove:")

    def _finish_build(self):
        if self.dh.jobPassed():
            self.setStatus(200, "Build complete")
        else:
            detail = 'Build job had failures:\n'
            for trv in sorted(self.buildJob.iterPrimaryFailureTroves()):
                fail = trv.getFailureReason()
                detail += '   * %s: %s\n' % (trv.getName(), fail)
            self.buildJob.jobFailed(detail)
            self.setStatus(400, "Build failed", detail)

        self.build_pending.callback('done')
        self.build_pending = None


TroveBuildJob = types.slottype('TroveBuildJob',
        'trove buildReqs crossReqs targetLabel builtTroves')


def register():
    handler.registerHandler(BuildHandler)
