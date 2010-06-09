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
from rmake.lib import repocache


class LoadTask(object):

    def run(self):
        self.job = self.task.task_data.thaw()
        self.log.info("Loading %d troves", len(self.job.troves))
        raise RuntimeError("oops")

        repos = conaryclient.ConaryClient(self.job.getMainConfig()).getRepos()
        if self.cfg.useCache:
            repos = repocache.CachingTroveSource(repos, self.cfg.getCacheDir())
