#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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
                                                               socket.getfqdn(),
                                                               message))
        if self['channel']:
            for channel in self['channel'].split(','):
                self.conn.write('inchan %s say [%s] %s\n' % (channel,
                                                             socket.getfqdn(),
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
