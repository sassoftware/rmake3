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
    xmppPermissive      = (cfgtypes.CfgBool, False,
            "Allow any node to connect to this one without authentication.")
    xmppPermit          = (cfgtypes.CfgList(CfgJID), [],
            "List of nodes permitted to connect to this one.")


class BusClientConfig(BusConfig):

    # XMPP
    dispatcherJID       = (CfgJID, None,
            "JID of the dispatcher to which this component should connect.")
