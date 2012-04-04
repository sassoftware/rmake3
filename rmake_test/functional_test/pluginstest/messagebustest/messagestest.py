
from rmake_test import rmakehelp


class MessagesTest(rmakehelp.RmakeHelper):

    def importPlugins(self):
        global messages
        from rmake.messagebus import messages

    def testMessages(self):
        # NOTE: underlying message format is likely to change.
        class MyMessage(messages.Message):
            def set(self, **args):
                self.payload.__dict__.update(args)

        m = MyMessage()
        m.set(a=3, b=4)
        headers, payloadStream, payloadSize = m.freeze()
        m2 = MyMessage()
        m2.loadPayloadFromString(payloadStream.read(payloadSize))
        assert(m2.payload.a == 3)
        assert(m2.payload.b == 4)

