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


import os
from conary.conarycfg import CfgUserInfo
from conary.lib.cfgtypes import CfgInt, CfgPath, CfgString
from rmake.messagebus.config import BusConfig


def _logPath(fileName):
    return property(lambda self: os.path.join(self.logDir, fileName))


class DispatcherConfig(BusConfig):

    # Server configuration
    databaseUrl         = (CfgString, 'postgres://rmake')
    listenAddress       = (CfgString, '::')
    listenPort          = (CfgInt, 9999)
    listenPath          = (CfgString, '/var/lib/rmake/socket')

    # Ancilliary components
    proxyUrl            = (CfgString, 'http://LOCAL:7778/')
    reposUrl            = (CfgString, 'http://LOCAL:7777/')
    reposUser           = (CfgUserInfo, None)
    reposName           = (CfgString, None)

    # Other configuration
    logDir              = (CfgPath, '/var/log/rmake')
    caCertPath          = (CfgPath, None)
    sslCertPath         = (CfgPath, '/srv/rmake/certs/rmake-server-cert.pem')

    # Deprecated options (ignored)
    rmakeUrl            = None

    # Calculated paths
    logPath_http = _logPath('access.log')
    logPath_server = _logPath('server.log')
