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
