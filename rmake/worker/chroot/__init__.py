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
from rmake.lib import apiutils
from rmake.lib.apiutils import freeze, thaw


class Chroot(object):
    def __init__(self, host, path, jobId, troveTuple, active):
        self.host = host
        self.path = path
        if not jobId:
            jobId = 0
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
