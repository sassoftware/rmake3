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


"""
Daemon entry point for the rMake worker node.
"""

import sys
from conary.lib import options
from rmake import compat
from rmake.lib import daemon
from rmake.worker import launcher


class WorkerDaemon(daemon.DaemonService, daemon.LoggingMixin,
        daemon.PluginsMixin):

    name = 'rmake-node'
    configClass = launcher.WorkerConfig
    logFileName = 'rmake-node.log'
    pluginTypes = ('launcher', 'worker')

    def setup(self, **kwargs):
        for name in ('dispatcherJID', 'xmppIdentFile'):
            if self.cfg[name] is None:
                sys.exit("error: Configuration option %r must be set." % name)

        srv = launcher.LauncherService(self.cfg, self.plugins,
                debug=kwargs['debug'])
        srv.setServiceParent(self)
        if self.cfg.xmppDebug:
            srv.bus.logTraffic = True

        super(WorkerDaemon, self).setup(**kwargs)

    def targetConnected(self, myJID, targetJID):
        pass


def main():
    compat.checkRequiredVersions()
    d = WorkerDaemon()
    try:
        return d.main()
    except options.OptionError, err:
        d.usage()
        print >> sys.stderr, 'error:', str(err)
