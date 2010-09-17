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

from conary.lib import cfgtypes
from conary.lib.cfg import ConfigFile
from twisted.words.protocols.jabber.jid import internJID


class CfgJID(cfgtypes.CfgType):

    full = None

    def parseString(self, val):
        try:
            val = internJID(val)
        except:
            raise cfgtypes.ParseError("Invalid JID")
        if self.full is True and val.resource is None:
            raise cfgtypes.ParseError("Expected a full JID")
        elif self.full is False:
            val = val.userhostJID()
        return val

    @staticmethod
    def format(val, displayOptions=None):
        return val.full()


class CfgFullJID(CfgJID):
    full = True


class BusConfig(ConfigFile):

    # XMPP
    xmppHost            = (cfgtypes.CfgString, None,
            "Override the host to connect to.")
    xmppJID             = (CfgFullJID, None,
            "Full JID that the component will identify as. (optional)")
    xmppIdentFile       = (cfgtypes.CfgPath, None,
            "File in which the component will store its JID and password.")
    xmppDebug           = (cfgtypes.CfgBool, False,
            "Log XMPP traffic")


class BusClientConfig(BusConfig):

    # XMPP
    dispatcherJID       = (CfgJID, None,
            "JID of the dispatcher to which this component should connect.")
