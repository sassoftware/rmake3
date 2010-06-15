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
Implementations of trove building tasks that are run on the worker node.
"""

from conary import conaryclient
from rmake.lib import recipeutil
#from rmake.lib import repocache
from rmake.worker import plug_worker


class LoadTask(plug_worker.TaskHandler):

    def run(self):
        from rmake.lib import logger
        logger.setupLogging(consoleLevel=logger.logging.DEBUG)
        job = self.task.task_data.thaw()
        job._log = self.log
        self.log.info("Loading %d troves", len(job.troves))

        repos = conaryclient.ConaryClient(job.getMainConfig()).getRepos()
        # TODO
        # if self.cfg.useCache:
        #    repos = repocache.CachingTroveSource(repos, self.cfg.getCacheDir())

        troves = [job.getTrove(*x) for x in job.iterLoadableTroveList()]
        if troves:
            self.sendStatus(101, "Loading troves")
            result = recipeutil.getSourceTrovesFromJob(job, troves, repos,
                    job.configs[''].reposName)
        self.sendStatus(200, "Troves loaded")
