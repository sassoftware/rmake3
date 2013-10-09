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
    xmppPort            = (cfgtypes.CfgInt, 5222)
    xmppSecure          = (cfgtypes.CfgBool, True,
            "Secure the XMPP connection with TLS")


class BusClientConfig(BusConfig):

    # XMPP
    dispatcherJID       = (CfgJID, None,
            "JID of the dispatcher to which this component should connect.")
