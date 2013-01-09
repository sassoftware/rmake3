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
