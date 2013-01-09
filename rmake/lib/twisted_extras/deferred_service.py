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
