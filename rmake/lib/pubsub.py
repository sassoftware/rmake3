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
Generic publish-subscribe mechanism.
"""


class Publisher(object):
    """Generic publisher mechanism."""

    def __init__(self):
        self._observers = {}
        self._relays = []

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        self.__init__()

    def addObserver(self, event, func):
        """Add "func" as an observer to "event"."""
        self._observers.setdefault(event, []).append(func)

    def delObserver(self, event, func):
        """Remove "func" as an observer to "event"."""
        self._observers.setdefault(event, []).remove(func)

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
