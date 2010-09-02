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
