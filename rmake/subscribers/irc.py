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


import urllib
import telnetlib
import socket

from rmake.build import buildjob
from rmake.build import buildtrove
from rmake.lib.subscriber import StatusSubscriber


class IRCJobLogger(StatusSubscriber):
    """
        Proof of concept irc updater for rmake.
    """

    protocol = 'irc'

    listeners = {'JOB_STATE_UPDATED'    : 'jobStateUpdated',
                 'TROVE_STATE_UPDATED'  : 'troveStateUpdated' }

    fields = {
        'channel'  : '',
        'nick'     : '',
        }

    def _connect(self):
        if not (self['channel'] or self['nick']):
            raise RuntimeError, 'Must specify either channel or nick'
        host, port = urllib.splitport(self.uri)
        self.conn = telnetlib.Telnet(host, port)

    def _sendMessage(self, message):
        self._connect()
        if self['nick']:
            for nick in self['nick'].split(','):
                self.conn.write('raw privmsg %s :[%s] %s\n' % (nick,
                                                           socket.gethostname(),
                                                           message))
        if self['channel']:
            for channel in self['channel'].split(','):
                self.conn.write('inchan %s say [%s] %s\n' % (channel,
                                                         socket.gethostname(),
                                                         message))
        self.conn.close()

    def jobStateUpdated(self, jobId, state, status):
        state = buildjob._getStateName(state)
        self._sendMessage('[jobId %d] - %s' % (jobId, state))

    def troveStateUpdated(self, (jobId, troveTuple), state, status):
        if state == buildtrove.TROVE_STATE_BUILDING:
            self._sendMessage('[jobId %s] - %s Building' % (jobId,
                                                            troveTuple[0]))
        elif state == buildtrove.TROVE_STATE_BUILT:
            self._sendMessage('[jobId %s] - %s Built' % (jobId, troveTuple[0]))
        elif state == buildtrove.TROVE_STATE_FAILED:
            self._sendMessage('[jobId %s] - %s Failed' % (jobId, troveTuple[0]))
