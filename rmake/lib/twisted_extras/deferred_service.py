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


"""
Add a "postStartService" method to Service/MultiService that is called after
the reactor is started. Implementations may return a Deferred, and if any
service fails to start then the process will be shut down.
"""


from twisted.application import service
from twisted.internet import defer


class Service(service.Service):

    def postStartService(self):
        pass


class MultiService(service.MultiService):

    def postStartService(self):
        l = []
        for service in self:
            if hasattr(service, 'postStartService'):
                l.append(defer.maybeDeferred(service.postStartService))
        d = defer.DeferredList(l, fireOnOneErrback=True, consumeErrors=True)

        def unwrap(reason):
            # Pull the failure out of the FirstError wrapper added by DL
            reason.trap(defer.FirstError)
            return reason.value.subFailure
        d.addErrback(unwrap)
        return d
