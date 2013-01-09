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
