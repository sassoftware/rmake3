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


import base64
import logging
from twisted.words.protocols.jabber.xmlstream import IQ

from rmake.lib.jabberlink import constants

log = logging.getLogger(__name__)


class Message(object):

    max_frame = 32768

    def __init__(self, message_type, payload='', headers=(), in_reply_to=None,
            more=False, seq=None):
        self.message_type = message_type
        self.payload = payload
        self.headers = dict(headers)
        if isinstance(in_reply_to, Message):
            assert in_reply_to.seq is not None
            in_reply_to = in_reply_to.seq
        self.in_reply_to = in_reply_to
        self.more = more
        self.seq = seq

        self.sender = None

    def split(self, seq):
        self.seq = seq
        payload = base64.b64encode(self.payload)
        frame_size = self.max_frame
        count = max(1, (len(payload) + frame_size - 1) / frame_size)
        out = []
        for n in range(count):
            chunk, payload = payload[:frame_size], payload[frame_size:]
            if n == 0:
                # Headers in the first chunk only
                headers = dict(self.headers)
                headers['type'] = unicode(self.message_type)
                headers['transport-encoding'] = 'base64'
                if self.in_reply_to is not None:
                    headers['in-reply-to'] = unicode(self.in_reply_to)
                if self.more:
                    headers['more'] = 'true'
            else:
                headers = ()
            # "more" in all but the last chunk
            more = n < (count - 1)
            out.append(Frame(seq + n, headers, chunk, more))
        assert not payload
        return out

    @classmethod
    def join(cls, frames):
        assert not frames[-1].more
        headers = {}
        for frame in frames:
            headers.update(frame.headers)
        payload = ''.join(x.payload for x in frames)

        message_type = headers.pop('type')
        transport_encoding = headers.pop('transport-encoding')
        in_reply_to = headers.pop('in-reply-to', None)
        if in_reply_to is not None:
            in_reply_to = long(in_reply_to)
        more = headers.pop('more', '').lower() == 'true'

        if transport_encoding == 'base64':
            payload = base64.b64decode(payload)
        else:
            log.error("Discarding message with unknown payload coding %r" %
                    (transport_encoding,))
            return None
        return cls(message_type, payload, headers, in_reply_to, more,
                frames[0].seq)


class Frame(object):

    def __init__(self, seq, headers=(), payload='', more=False):
        self.seq = seq
        self.headers = dict(headers)
        self.payload = payload
        self.more = more

    def to_dom(self, xmlstream):
        iq = IQ(xmlstream, 'set')
        frame = iq.addElement('frame', constants.NS_JABBERLINK)
        frame['seq'] = unicode(self.seq)
        if self.more:
            frame['more'] = 'true'
        if self.headers:
            message = frame.addElement('message')
            for name, value in self.headers.items():
                message[name] = unicode(value)
        if self.payload:
            payload = frame.addElement('payload')
            payload.addContent(self.payload)
        return iq

    @classmethod
    def from_dom(cls, iq):
        headers = {}
        payload = ''

        frame = iq.firstChildElement()
        seq = long(frame['seq'])
        more = frame.getAttribute('more', '').lower() == 'true'

        for child in frame.elements():
            if child.name == 'message':
                for key, value in child.attributes.items():
                    headers[key] = value
            elif child.name == 'payload':
                payload = str(child)

        return cls(seq, headers, payload, more)


class MessageHandler(object):

    namespace = None

    def onMessage(self, neighbor, message):
        pass
