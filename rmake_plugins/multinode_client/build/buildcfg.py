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


import urllib

from conary.lib import cfgtypes

from rmake.build import buildcfg
from rmake.lib import apiutils

class BuildContext(object):
    rmakeUrl  = (cfgtypes.CfgString, 'unix:///var/lib/rmake/socket')
    rmakeUser = (buildcfg.CfgUser, None)
    clientCert = (cfgtypes.CfgPath, None)

def getServerUri(self):
    url = self.rmakeUrl
    type, rest = urllib.splittype(url)
    if type != 'unix':
        host, path = urllib.splithost(rest)
        user, host = urllib.splituser(host)
        host, port = urllib.splitport(host)
        if not port:
            port = 9999
        user = ''
        if self.rmakeUser:
            user = '%s:%s@'  % (self.rmakeUser)

        url = '%s://%s%s:%s%s' % (type, user, host, port, path)
    return url

def updateConfig():
    buildcfg.RmakeBuildContext.rmakeUrl = BuildContext.rmakeUrl
    buildcfg.RmakeBuildContext.rmakeUser = BuildContext.rmakeUser
    buildcfg.RmakeBuildContext.clientCert = BuildContext.clientCert
    buildcfg.BuildConfiguration.getServerUri = getServerUri

class SanitizedBuildConfiguration(buildcfg.SanitizedBuildConfiguration):

    @staticmethod
    def __freeze__(cfg):
        cfg = buildcfg.SanitizedBuildConfiguration.__freeze__(cfg)
        if 'rmakeUser' in cfg:
            del cfg['rmakeUser']
        return cfg

    @staticmethod
    def __thaw__(cfg):
        return apiutils.thaw('BuildConfiguration', cfg)
apiutils.register(SanitizedBuildConfiguration)
