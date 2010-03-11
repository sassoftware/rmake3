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


"""
Constants and simple functions shared by message bus components.
"""

from twisted.words.protocols.jabber.jid import internJID, JID
from wokkel import data_form


# Element namespaces
NS_RMAKE = 'http://rpath.com/permanent/xmpp/rmake-3.0'

# XPath expressions
XPATH_RMAKE_MESSAGE = "/message/rmake[@xmlns='%s']" % NS_RMAKE
XPATH_RMAKE_IQ = "/iq/rmake[@xmlns='%s']" % NS_RMAKE

# Data form namespaces
FORM_RMAKE_INFO = 'http://rpath.com/permanent/xmpp/rmake-3.0#info'


def toJID(jid):
    if isinstance(jid, basestring):
        return internJID(jid)
    elif isinstance(jid, JID):
        return jid
    else:
        raise TypeError("Expected a JID (string or JID object)")


def getInfoForm(role):
    form = data_form.Form('result', formNamespace=FORM_RMAKE_INFO)

    assert role in ('dispatcher', 'server', 'worker')
    form.addField(data_form.Field(var='role', value=role))

    return form
