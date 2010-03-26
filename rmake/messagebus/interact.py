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
#

import logging
from twisted.internet import defer
from twisted.words.protocols.jabber.xmlstream import XMPPHandler, toResponse
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

    def interact_help(self, msg, words):
        return "I can't help you right now."
