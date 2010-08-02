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
Daemon entry point for the rMake dispatcher.
"""


import sys
from conary.lib import options
from rmake import compat
from rmake.core.config import DispatcherConfig
from rmake.core.dispatcher import Dispatcher
from rmake.lib import daemon
from rmake.lib import osutil


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
        osutil.setproctitle('rmake-dispatcher ' +
                self.cfg.xmppJID.full().encode('utf-8'))

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
