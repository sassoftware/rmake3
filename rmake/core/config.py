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


import os
from conary.conarycfg import CfgUserInfo
from conary.lib.cfgtypes import (CfgBool, CfgDict, CfgInt, CfgPath,
        CfgPathList, CfgString, CfgList)
from rmake.messagebus.config import BusConfig


def _path(attr, fileName):
    return property(lambda self: os.path.join(getattr(self, attr), fileName))


class DispatcherConfig(BusConfig):

    # Server configuration
    databaseUrl         = (CfgString, 'postgres://rmake')
    listenAddress       = (CfgString, '::')
    listenPort          = (CfgInt, 9999)
    listenPath          = (CfgString, '/var/lib/rmake/socket')
    dataDir             = (CfgPath, '/srv/rmake')

    # Ancilliary components
    proxyUrl            = (CfgString, 'http://LOCAL:7778/')
    reposUrl            = (CfgString, 'http://LOCAL:7777/')
    reposUser           = (CfgUserInfo, None)
    reposName           = (CfgString, None)

    # Other configuration
    logDir              = (CfgPath, '/var/log/rmake')
    caCertPath          = (CfgPath, None)
    sslCertPath         = (CfgPath, '/srv/rmake/certs/rmake-server-cert.pem')

    # Plugins
    pluginDirs          = (CfgPathList, [])
    pluginOption        = (CfgDict(CfgList(CfgString)), {})
    usePlugin           = (CfgDict(CfgBool), {})

    # Calculated paths
    logPath_http = _path('logDir', 'access.log')
    logPath_server = _path('logDir', 'server.log')
    lockDir = _path('dataDir', 'lock')
    jobLogDir = _path('dataDir', 'logs')
