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


from twisted.words.protocols.jabber.jid import internJID, JID


def toJID(jid):
    if isinstance(jid, basestring):
        return internJID(jid)
    elif isinstance(jid, JID):
        return jid
    else:
        raise TypeError("Expected a JID (string or JID object)")
