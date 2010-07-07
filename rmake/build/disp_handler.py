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

"""
Job handler used by the dispatcher to run trove build jobs.
"""

import logging
from rmake.build import buildjob
from rmake.build import constants as buildconst
from rmake.build import dephandler
from rmake.build.publisher import JobStatusPublisher
from rmake.core import handler

log = logging.getLogger(__name__)


class BuildHandler(handler.JobHandler):
    __slots__ = ('build_plugin', 'cfg', 'dh')

    jobType = buildconst.BUILD_JOB
    firstState = 'load_troves'

    def setup(self):
        self.build_plugin = self.dispatcher.plugins.getPlugin('build')
        self.cfg = self.build_plugin.cfg
        self.dh = None

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
        publisher = JobStatusPublisher()
        job.setPublisher(publisher)
        logger = logging.getLogger('dephandler.' + self.job.job_uuid.short)
        self.dh = dephandler.DependencyHandler(publisher, logger, troves)

        # TODO: sanity check

        self.setData(job)
        return 'build'

    def build(self):
        self.setStatus(101, "Building troves")
        self.setStatus(400, "Oops")


def register():
    handler.registerHandler(BuildHandler)
