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
