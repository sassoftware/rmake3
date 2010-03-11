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


class Subscriber(object):
    """Generic subscriber mechanism.

    Define a "handle_foo" method to process incoming "foo" events.
    """

    def _doEvent(self, event, *args, **kwargs):
        func = getattr(self, 'handle_' + event, None)
        if func:
            func(*args, **kwargs)


class Publisher(object):
    """Generic publisher mechanism.

    Instances of Subscriber are subscribed to this publisher, and each time any
    event is fired all subscribers are invoked.  Subscribers are stored using
    weak references so the caller must maintain their own strong reference to
    each subscriber.
    """

    def __init__(self):
        self.subscribers = []

    def subscribe(self, subscriber):
        for sub in self.subscribers:
            if sub is subscriber:
                return
        self.subscribers.append(subscriber)

    def unsubscribe(self, subscriber):
        for sub in self.subscribers[:]:
            if sub is subscriber:
                self.subscribers.remove(sub)

    def _send(self, event, *args, **kwargs):
        for sub in self.subscribers:
            sub._doEvent(event, *args, **kwargs)
