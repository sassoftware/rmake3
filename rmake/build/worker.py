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
        buildJob = self.task.task_data.getObject()
        self.log.info("Building trove %s", buildJob.trove.getTroveString())
