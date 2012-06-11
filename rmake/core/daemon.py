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
Daemon entry point for the rMake dispatcher.
"""


import sys
from conary.lib import options
from rmake import compat
from rmake.core.config import DispatcherConfig
from rmake.core.dispatcher import Dispatcher
from rmake.lib import daemon


class DispatcherDaemon(daemon.DaemonService, daemon.LoggingMixin,
        daemon.PluginsMixin):

    name = 'rmake-dispatcher'
    configClass = DispatcherConfig
    user = 'rmake'
    groups = ['rmake']
    logFileName = 'dispatcher.log'
    pluginTypes = ('dispatcher',)

    def setup(self, **kwargs):
        for name in ('xmppJID', 'xmppIdentFile'):
            if self.cfg[name] is None:
                sys.exit("error: Configuration option %r must be set." % name)

        srv = Dispatcher(self.cfg, self.plugins)
        srv.setServiceParent(self)
        if self.cfg.xmppDebug:
            srv.bus.logTraffic = True

        # Call super *after* adding services.
        super(DispatcherDaemon, self).setup(**kwargs)


def main():
    compat.checkRequiredVersions()
    d = DispatcherDaemon()
    try:
        return d.main()
    except options.OptionError, err:
        d.usage()
        print >> sys.stderr, 'error:', str(err)
