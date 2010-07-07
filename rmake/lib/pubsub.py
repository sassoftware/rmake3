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
Generic publish-subscribe mechanism.
"""


class Publisher(object):
    """Generic publisher mechanism."""

    def __init__(self):
        self._observers = {}
        self._relays = []

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        self.__init__()

    def addObserver(self, event, func):
        """Add "func" as an observer to "event"."""
        self._observers.setdefault(event, []).append(func)

    def addRelay(self, func):
        """Add "func" as an observer to all events.

        It will be called with the event name as the first argument.
        """
        self._relays.append(func)

    def _send(self, event, *args, **kwargs):
        for func in self._observers.get(event, ()):
            func(*args, **kwargs)
        for func in self._relays:
            func(event, *args, **kwargs)
