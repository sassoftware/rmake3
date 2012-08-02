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

from twisted.internet import defer


class Serializer(object):

    def __init__(self):
        self._lock = defer.DeferredLock()
        self._waiting = {}

    def call(self, func, collapsible=False):
        d = self._lock.acquire()
        self._waiting[d] = collapsible
        @d.addCallback
        def _locked(_):
            if collapsible and len(self._waiting) > 1:
                # Superseded
                return
            return func()
        @d.addBoth
        def _unlock(result):
            self._lock.release()
            del self._waiting[d]
            return result
        return d
