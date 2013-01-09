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


from rmake.lib.apiutils import thaw, freeze, register
from rmake.lib import apiutils

class Node(object):
    def __init__(self, name, hostname, slots, flavors, active, chroots=[]):
        self.name = name
        self.hostname = hostname
        self.slots = slots
        self.flavors = flavors
        self.active = active
        self.chroots = chroots

    @staticmethod
    def __freeze__(self):
        return dict(hostname=self.hostname, 
                    flavors=[ freeze('flavor', x) for x in self.flavors ],
                    name=self.name,  active=self.active, slots=self.slots,
                    chroots=[ freeze('Chroot', x) for x in self.chroots])

    @classmethod
    def __thaw__(class_, d):
        self = class_(**d)
        self.chroots = [ thaw('Chroot', x) for x in self.chroots ]
        self.flavors = [ thaw('flavor', x) for x in self.flavors ]
        return self

    def addChroot(self, chroot):
        self.chroots.append(chroot)
apiutils.register(Node)
