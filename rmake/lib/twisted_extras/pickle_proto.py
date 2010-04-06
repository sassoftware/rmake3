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

import cPickle
import logging
from twisted.protocols.basic import Int32StringReceiver

log = logging.getLogger(__name__)


class PickleProtocol(Int32StringReceiver):

    def stringReceived(self, data):
        log.debug("Pickle from %s", self.transport.getPeer())
        try:
            obj = cPickle.loads(data)
        except:
            log.exception("Error unpickling data from %s, disconnecting:",
                    self.transport.getPeer())
            self.transport.loseConnection()
        else:
            self.messageReceived(obj)

    def sendMessage(self, obj):
        self.sendString(cPickle.dumps(obj, 2))
