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
from rmake.lib import repocache
from rmake.worker import plug_worker
from rmake.worker import resolver


class _BuilderTask(plug_worker.TaskHandler):

    cfg = None  # poked in by BuildPlugin

    def run(self):
        from rmake.lib import logger
        logger.setupLogging(consoleLevel=logger.logging.DEBUG)

        self.run_builder(self.getData())


class LoadTask(_BuilderTask):

    def run_builder(self, job):
        job._log = self.log
        self.log.info("Loading %d troves", len(job.troves))

        repos = conaryclient.ConaryClient(job.getMainConfig()).getRepos()
        if self.cfg.useCache:
           repos = repocache.CachingTroveSource(repos, self.cfg.getCacheDir())

        troves = [job.getTrove(*x) for x in job.iterLoadableTroveList()]
        if troves:
            self.sendStatus(101, "Loading troves")
            recipeutil.loadSourceTrovesForJob(job, troves, repos,
                    job.configs[''].reposName)

        # Check if any troves failed to load
        errors = []
        for trove in troves:
            if not trove.isFailed():
                continue
            reason = trove.getFailureReason()
            out = 'Trove failed to load: %s\n%s' % (
                    trove.getTroveString(withContext=True),
                    trove.getFailureReason())
            if reason.hasTraceback():
                out += '\n\n' + reason.getTraceback()
            errors.append(out)
        if errors:
            detail = '\n'.join(errors)
            self.sendStatus(400, "Some troves failed to load", detail)
            return

        # Post updated job object back to the dispatcher
        job._log = None
        self.setData(job)
        self.sendStatus(200, "Troves loaded")


class ResolveTask(_BuilderTask):

    def run_builder(self, resolveJob):
        self.log.info("Resolving trove %s", resolveJob.trove.getTroveString())

        client = conaryclient.ConaryClient(resolveJob.getConfig())
        repos = client.getRepos()
        if self.cfg.useCache:
           repos = repocache.CachingTroveSource(repos, self.cfg.getCacheDir())

        rsv = resolver.DependencyResolver(self.log, repos)
        result = rsv.resolve(resolveJob)

        self.setData(result)
        self.sendStatus(200, "Resolution completed")


class BuildTask(_BuilderTask):

    def run_builder(self, job):
        from rmake.lib import logger
        logger.setupLogging(consoleLevel=logger.logging.DEBUG)
        buildJob = self.task.task_data.thaw()
        self.log.info("Building trove %s", buildJob.trove.getTroveString())
