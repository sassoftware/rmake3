#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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
