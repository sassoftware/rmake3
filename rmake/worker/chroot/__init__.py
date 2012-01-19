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
