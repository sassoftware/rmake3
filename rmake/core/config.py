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
