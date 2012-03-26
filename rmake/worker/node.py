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
