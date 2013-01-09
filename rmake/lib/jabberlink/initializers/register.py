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


import logging
from twisted.internet import defer
from twisted.words.protocols.jabber import sasl
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber import client as jclient

log = logging.getLogger(__name__)


class RegisteringInitializer(object):

    def __init__(self, xmlstream, callback):
        self.xmlstream = xmlstream
        self.callback = callback
        self._inProgress = None

    def initialize(self):
        si = sasl.SASLInitiatingInitializer(self.xmlstream)
        d = si.initialize()
        d.addErrback(self.saslFailed)
        return d

    def saslFailed(self, reason):
        return self.registerAccount()

    def registerAccount(self):
        assert not self._inProgress
        auth = self.xmlstream.authenticator

        iq = jclient.IQ(self.xmlstream, 'set')
        iq.addElement(('jabber:iq:register', 'query'))
        iq.query.addElement('username', content=auth.jid.user)
        iq.query.addElement('password', content=auth.password)

        iq.addCallback(self._registerResultEvent)
        iq.send()

        d = defer.Deferred()
        self._inProgress = (d, auth.jid, auth.password)
        return d

    def _registerResultEvent(self, iq):
        init_d, jid, password = self._inProgress
        self._inProgress = None
        if iq['type'] == 'result':
            d = defer.maybeDeferred(self.callback, jid, password)

            # Now that we're registered, reconnect so we can identify.
            @d.addCallback
            def after_callback(dummy):
                log.info("Successfully registered account %s", jid.userhost())
                self.xmlstream.factory.setReconnecting()
                self.xmlstream.transport.loseConnection()
                return xmlstream.Reset
            d.chainDeferred(init_d)

        elif iq['type'] == 'error':
            jid = self.xmlstream.authenticator.jid.userhost()
            error = iq.error.firstChildElement().name
            if error == 'conflict':
                log.error("Registration of JID %s failed because it is "
                        "already registered. This means that the stored "
                        "password is incorrect.", jid)
            else:
                log.error("Registration of JID %s failed (%s).", jid, error)
            init_d.errback(RegistrationFailedError(
                "Registration failed: %s" % error))


class RegisteringAuthenticator(xmlstream.ConnectAuthenticator):

    namespace = 'jabber:client'

    def __init__(self, jid, password, registerCB):
        xmlstream.ConnectAuthenticator.__init__(self, jid.host)
        self.jid = jid
        self.password = password
        self.registerCB = registerCB

    def associateWithStream(self, xs):
        xmlstream.ConnectAuthenticator.associateWithStream(self, xs)

        xs.initializers = [
                xmlstream.TLSInitiatingInitializer(xs),
                RegisteringInitializer(xs, self.registerCB),
                ]

        for initClass, required in [
                (jclient.BindInitializer, True),
                (jclient.SessionInitializer, False),
                ]:
            init = initClass(xs)
            init.required = required
            xs.initializers.append(init)


class RegistrationFailedError(RuntimeError):
    pass
