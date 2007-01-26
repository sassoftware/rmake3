#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
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
