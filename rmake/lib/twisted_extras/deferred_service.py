#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
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
