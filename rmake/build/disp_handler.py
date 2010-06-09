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
from rmake.core import handler

log = logging.getLogger(__name__)


class BuildHandler(handler.JobHandler):
    __slots__ = ('cfg', 'pending')

    jobType = buildconst.BUILD_JOB
    firstState = 'loading'

    def setup(self):
        build_plugin = self.dispatcher.plugins.getPlugin('build')
        self.cfg = build_plugin.cfg

    def begin_loading(self):
        self.pending = set()
        job = self.job.data

        for cfg in job.iterConfigList():
            cfg.repositoryMap.update(self.cfg.getRepositoryMap())
            cfg.user.extend(self.cfg.reposUser)
            cfg.reposName = self.cfg.reposName

        for troveTup in job.getMainConfig().primaryTroves:
            job.getTrove(*troveTup).setPrimaryTrove()

        # Start a load trove task
        loadTroves = job.troves.values()
        assert not [x for x in loadTroves if x.isSpecial()]
        self.setStatus(buildjob.JOB_STATE_LOADING,
                'Loading %d troves' % len(loadTroves))
        task, dummy = self.newTask('load', buildconst.LOAD_TASK, job)
        self.pending.add(task.task_uuid)

        # Stash the updated job back into the database.
        d = self.updateJobData()
        self.pending.add('data update')
        @d.addCallback
        def data_updated(dummy):
            self._continue(('data updated',))
        d.addErrback(self.failJob, message="Error updating job data:")

    def continue_loading(self, event):
        evtype = event[0]
        if evtype == 'data updated':
            self.pending.discard('data update')
        elif evtype == 'task updated':
            task = event[1]
            if not task.status.final:
                return
            self.pending.discard(task.task_uuid)
            if task.status.failed:
                return self.setStatus(400, text=task.status.text,
                        detail=task.status.detail, state='done')
        else:
            return

        if self.pending:
            return

        return self.setStatus(200, text='oh yay', state='done')


def register():
    handler.registerHandler(BuildHandler)
