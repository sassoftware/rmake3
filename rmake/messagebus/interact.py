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


import logging
from twisted.internet import defer
from twisted.words.protocols.jabber.jid import JID
from twisted.words.protocols.jabber.xmlstream import XMPPHandler, toResponse
from twisted.words.xish import domish
from twisted.words.xish import xpath
from rmake.messagebus import common

log = logging.getLogger(__name__)


class InteractiveHandler(XMPPHandler):

    def connectionInitialized(self):
        self.xmlstream.addObserver(common.XPATH_IM, self.messageReceived)

    def messageReceived(self, element):
        body = unicode(xpath.queryForNodes('/message/body', element)[0])
        words = body.split()
        command = words.pop(0).encode('ascii', 'replace')

        func = getattr(self, 'interact_' + command, None)
        if func:
            d = defer.maybeDeferred(func, element, words)
        else:
            d = defer.succeed(u"Unknown command '%s'. Try 'help'."
                    % (command,))

        def on_error(failure):
            log.error("Error in interactive handler '%s':\n%s", command,
                    failure.getTraceback())
            return (u'An internal error occurred in the rMake server. '
                    u'Please check the server logs for more information.')

        def on_reply(reply):
            if reply is None:
                reply = 'OK'
            msg = toResponse(element, 'chat')
            msg.addElement('body', content=unicode(reply))
            threads = xpath.queryForNodes('/message/thread', element)
            if threads:
                msg.addChild(threads[0])
            self.send(msg)

        d.addErrback(on_error)
        d.addCallback(on_reply)

    def sendMessage(self, targetOrMessage, text, type='normal'):
        msg = domish.Element((None, 'message'))
        if isinstance(targetOrMessage, JID):
            # New message
            msg['to'] = targetOrMessage.full()
            msg['type'] = type
        elif isinstance(targetOrMessage, domish.Element):
            # Reply to a previous message
            msg['to'] = targetOrMessage['from']
            msg['type'] = targetOrMessage['type']
            threads = xpath.queryForNodes('/message/thread', targetOrMessage)
            if threads:
                msg.addChild(threads[0])
        else:
            raise TypeError("Expected JID or Element")
        msg.addElement('body', content=unicode(text))
        self.send(msg)

    def interact_help(self, msg, words):
        """List available commands."""
        commands = ['Available commands:']
        for name in sorted(dir(self)):
            if name[:9] != 'interact_':
                continue
            cmd = name[9:]

            func = getattr(self, name)
            doc = ''
            if func.__doc__:
                for line in func.__doc__.splitlines():
                    if line.strip():
                        doc = line.strip()
                        break

            commands.append('%s\t%s' % (cmd, doc))
        return '\n'.join(commands)
