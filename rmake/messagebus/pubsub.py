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
Publishing shims for message bus clients.
"""

import weakref
from rmake.lib import pubsub
from rmake.messagebus.message import Event


class BusSubscriber(pubsub.Publisher):
    """Subscriber that forwards all events to a target subscriber."""

    def __init__(self, subsystem, xmlstream, targetJID):
        self.xmlstream = xmlstream
        self.subsystem = subsystem
        self.targetJID = targetJID

    def _doEvent(self, event, *args, **kwargs):
        msg = Event(subsystem=self.subsystem, event=event, args=args,
                kwargs=kwargs)
        msg.send(self.xmlstream, self.targetJID)
