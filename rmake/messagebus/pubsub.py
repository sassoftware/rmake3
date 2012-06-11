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
