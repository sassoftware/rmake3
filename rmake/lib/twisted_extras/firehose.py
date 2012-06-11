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
Tools for implementing a persistent streaming HTTP response.
"""

import cPickle
import httplib
import logging
import time
from collections import deque
from rmake import constants
from rmake.lib import uuid
from rmake.lib import rpcproxy
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

log = logging.getLogger(__name__)


class FirehoseSession(object):
    """A context in which a client monitors zero or more server events.

    The session persists the client's subscriptions across multiple
    connections, so that the client can recover from network errors without
    losing any messages.
    """

    def __init__(self, sid=None):
        if sid is None:
            sid = uuid.uuid4()
        self.sid = sid
        self.subscriptions = set()
        self.spool = deque()
        self.response = None
        self.time_detached = time.time()

    def attach(self, response):
        self.detach()
        self.response = response

        # Make sure we detach if the connection is lost.
        d = self.response.notifyFinish()
        d.addBoth(self._detached)

        # Send session details in the response headers.
        self.response.responseHeaders.setRawHeaders(
                'cache-control', [ 'no-cache' ])
        self.response.responseHeaders.setRawHeaders(
                'content-type', [ 'application/x-rmake-prefixed-pickle' ])
        self.response.responseHeaders.setRawHeaders(
                'x-rmake-session', [ str(self.sid) ])
        self.response.write('')

        # Flush any queued events.
        self._write()

    def detach(self):
        if self.response is None:
            return
        self.response.finish()
        self._detached()

    def send(self, event):
        try:
            data = cPickle.dumps(event, 2)
        except:
            log.exception("Error pickling firehose event:")
            return
        packed = '%s\r\n%s' % (len(data), data)
        self.spool.append(packed)
        self._write()

    def getIdleTime(self):
        if self.response is None:
            return time.time() - self.time_detached
        else:
            return 0

    def close(self):
        self.detach()
        self.subscriptions.clear()
        self.spool.clear()

    def _detached(self, dummy):
        self.response = None
        self.time_detached = time.time()
        log.debug("Detached session %s", self.sid)

    def _write(self):
        if self.spool and self.response:
            self.response.write(''.join(self.spool))
            self.spool.clear()


class FirehoseResource(Resource):

    MAX_IDLE_TIME = 600

    def __init__(self):
        self.sessions = {}

    def render_GET(self, request):
        session = self._makeSession(request.getHeader('x-rmake-session'))
        log.debug("Attached session %s", session.sid)
        session.attach(request)
        return NOT_DONE_YET

    def cleanup(self):
        for sid, session in self.sessions.items():
            if session.getIdleTime() > self.MAX_IDLE_TIME:
                log.debug("Freeing session %s", sid)
                session.close()
                del self.sessions[sid]

    def publish(self, event, data):
        log.debug("Published to %r: %r", event, data)
        for session in self.sessions.itervalues():
            matches = match_events(event, session.subscriptions)
            if matches:
                session.send(FirehoseEvent(event, data, matches))

    def subscribe(self, event, sid):
        session = self._makeSession(sid)
        session.subscriptions.add(event)
        log.debug("Subscribed %s to %r", session.sid, event)

    def _makeSession(self, sid=None):
        session = None
        if sid is not None:
            if not isinstance(sid, uuid.UUID):
                sid = uuid.UUID(sid)
            session = self.sessions.get(sid)
        if session is None:
            session = FirehoseSession(sid)
            self.sessions[session.sid] = session
        return session


class FirehoseEvent(object):
    """One event to be sent over the firehose.

    The "event" argument is a tuple that places the event in a hierarchy,
    e.g. ('job', 1234, 'status'). Clients can then subscribe to part of that
    hierarchy and receive events anywhere underneath it.
    """

    def __init__(self, event, data, matched=None):
        self.event = event
        self.data = data
        if matched is None:
            self.matched = None
        else:
            self.matched = set(matched)


def match_events(event, patterns):
    """Return a list of patterns that match the given event name."""
    matches = []
    for pattern in patterns:
        if match_one(event, pattern):
            matches.append(pattern)
    return matches


def match_one(event, pattern):
    """Test whether the given pattern matches the given event name."""
    assert isinstance(pattern, tuple)
    if pattern == event:
        return True
    elif len(pattern) > len(event):
        return False
    elif pattern == event[:len(pattern)]:
        return True
    else:
        return False


class FirehoseClient(object):

    userAgent = "rpath_rmake/%s (www.rpath.com)" % constants.version

    def __init__(self, url):
        if not isinstance(url, rpcproxy.Address):
            url = rpcproxy.parseAddress(url)
        assert url.schema == 'http'
        self.url = url
        self.sid = uuid.uuid4()
        self.conn = None
        self.buffer = ''

    def connect(self):
        if self.conn:
            return
        conn = httplib.HTTPConnection(self.url.host, self.url.port)
        conn.putrequest('GET', self.url.handler, skip_host=True,
                skip_accept_encoding=True)
        conn.putheader('Host', self.url.getHTTPHost())
        conn.putheader('User-Agent', self.userAgent)
        conn.putheader('Content-Length', '0')
        conn.putheader('X-Rmake-Session', str(self.sid))
        conn.endheaders()

        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError("HTTP status %s %s" % (resp.code, resp.reason))
        self.conn = resp

        self.buffer = ''
        self.next_chunk_total = None

    def iterAll(self):
        while True:
            self.connect()

            while True:
                if self.next_chunk_total is not None:
                    next = self.next_chunk_total - len(self.buffer)
                else:
                    next = 1
                data = self.conn.read(next)
                if not data:
                    self.conn.close()
                    self.conn = None
                    break
                self.buffer += data

                if '\r\n' not in self.buffer:
                    continue
                idx = self.buffer.index('\r\n')
                chunk_size = int(self.buffer[:idx])
                self.next_chunk_total = idx + 2 + chunk_size
                if len(self.buffer) < self.next_chunk_total:
                    continue
                event = self.buffer[idx + 2 : idx + 2 + next]
                self.buffer = self.buffer[idx + 2 + next :]
                self.next_chunk_total = None

                try:
                    event = cPickle.loads(event)
                except cPickle.UnpicklingError:
                    log.exception("Error unpickling firehose event:")
                    continue

                yield event
