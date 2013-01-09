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


from rmake.lib import apiutils
from rmake.lib.apiutils import freeze, thaw


class Chroot(object):
    def __init__(self, host, path, jobId, troveTuple, active):
        self.host = host
        self.path = path
        if not jobId:
            jobId = 0
        assert(path is not None)
        self.jobId = jobId
        self.troveTuple = troveTuple
        self.active = active

    def __freeze__(self):
        d = self.__dict__.copy()
        if self.troveTuple:
            d['troveTuple'] = freeze('troveTuple', self.troveTuple)
        else:
            d['troveTuple'] = ''
        return d

    @classmethod
    def __thaw__(class_, d):
        self = class_(**d)
        if self.troveTuple:
            self.troveTuple = thaw('troveTuple', self.troveTuple)
        else:
            self.troveTuple = None
        return self
apiutils.register(Chroot)
