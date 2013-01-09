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


from rmake_test import rmakehelp


import StringIO
import unittest

testFrozenLead1 = '\xbe\xeb\xab\xba\x04\x00\x00\x00\00\00\00\00\00\x00\x00\x02\x00\x01\x05\x00\x04\x00\x01\xe2@\x06\x00\x04\x00\x12\xd6\x87'

testFrozenLead2 = 'this is a bad lead that will miserably fail'

testFrozenHeader1 = 'content-type: binary/xml\n'

testFrozenMessage1 = '\xbe\xeb\xab\xba\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x01\x05\x00\x04\x00\x00\x00(\x06\x00\x04\x00\x00\x00\x16content-type: application/octect-stream\nThis is a test message'

testFrozenMessage2 = "\xbe\xeb\xab\xba\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x01\x05\x00\x04\x00\x00\x00'\x06\x00\x04\x00\x00\x00\x17content-type: application/binary-stuff\nFirst line\nSecond line\n"
testPayload1 = "This is a test message"

class EnvelopeTest(rmakehelp.RmakeHelper):

    def importPlugins(self):
        global envelope
        from rmake.messagebus import envelope

    msgPayloadSize = 1234567
    msgHeaderSize = 123456
    def testLeadFreeze(self):

        f = envelope.PLead()
        f.msgPayloadSize.set(self.msgPayloadSize)
        self.failUnlessEqual(f.msgPayloadSize(), self.msgPayloadSize)
        f.msgHeaderSize.set(self.msgHeaderSize)
        self.failUnlessEqual(f.msgHeaderSize(), self.msgHeaderSize)

        data = f.freeze()
        self.failUnlessEqual(data, testFrozenLead1)

    def testHeaderFreeze(self):
        f = envelope.PHeader()
        f['content-type'] = "binary/xml"
        data = f.freeze()

        self.failUnlessEqual(data, testFrozenHeader1)

        ff = envelope.PHeader()
        ff.thawString(data)
        self.failUnlessEqual(ff['content-type'], "binary/xml")

    def testLeadChunkedThaw(self):
        s1 = StringIO.StringIO(testFrozenLead1[:10])
        s2 = StringIO.StringIO(testFrozenLead1[10:])

        f = envelope.PLead()
        self.failIf(f.thawFromStream(s1.read))
        self.failUnless(f.thawFromStream(s2.read))

        self.failUnlessEqual(f.msgHeaderSize(), self.msgHeaderSize)
        self.failUnlessEqual(f.msgPayloadSize(), self.msgPayloadSize)

    def testLeadThawBad(self):
        f = envelope.PLead()
        self.failUnlessRaises(envelope.BadMagicError, f.thawString, testFrozenLead2)

    def testMessageThawLead(self):
        m = envelope.Envelope()

        s1 = StringIO.StringIO(testFrozenLead1[:10])
        s2 = StringIO.StringIO(testFrozenLead1[10:])

        self.failIf(m.thawLead(s1.read))
        self.failUnless(m.thawLead(s2.read))

    def testMessageThawHeader(self):
        m = envelope.Envelope()

        m.setHeaderSize(len(testFrozenHeader1))

        s1 = StringIO.StringIO(testFrozenHeader1[:4])
        s2 = StringIO.StringIO(testFrozenHeader1[4:])

        self.failIf(m.thawHeader(s1.read))
        self.failUnless(m.thawHeader(s2.read))

    def testMessageFreezeBasic(self):
        m = envelope.Envelope()
        payloadStream = StringIO.StringIO(testPayload1)

        m.setPayloadStream(payloadStream)
        m.setPayloadSize(len(testPayload1))
        payloadStream.seek(0)
        m.setContentType('application/octect-stream')

        data = m.freeze()
        self.failUnlessEqual(data, testFrozenMessage1)

    def testMessageThawBasic(self):
        m = envelope.Envelope()
        s = StringIO.StringIO(testFrozenMessage1)
        xx = m.thawFromStream(s.read, blocking=True)

        ss = m.getPayloadStream()
        self.failUnlessEqual(ss.read(), testPayload1)

    def testMessageThawChunked(self):
        # Tests chunked reads from the stream

        class ChunkedReadStream(object):
            def __init__(self, stream):
                self.stream = stream
                self.chunkSize = 3

            def read(self, size=None):
                toread = self.chunkSize
                if size:
                    toread = min(size, toread)
                return self.stream.read(toread)

        m = envelope.Envelope()
        s = StringIO.StringIO(testFrozenMessage1)

        cs = ChunkedReadStream(s)
        m.thawFromStream(cs.read, blocking=True)

        self.failUnlessEqual(m.readPayload(), testPayload1)

        # Same test, with chunked reads for thawing
        s.seek(0)
        while not m.thawFromStream(cs.read):
            pass

        self.failUnlessEqual(m.readPayload(10), testPayload1[:10])

        # Same test, testing hasComplete*
        s.seek(0)
        m.reset()

        leadSize = envelope.PLead.frozenSize

        bytesRead = 0
        while bytesRead < leadSize - cs.chunkSize:
            m.thawFromStream(cs.read)
            self.failIf(m.hasCompleteLead())
            bytesRead += cs.chunkSize

        m.thawFromStream(cs.read)
        self.failUnless(m.hasCompleteLead())

        self.failIf(m.hasCompleteHeader())

        # Header size
        hs = m.getHeaderSize()

        bytesRead = 0
        while bytesRead < hs - cs.chunkSize:
            m.thawFromStream(cs.read)
            self.failIf(m.hasCompleteHeader())
            bytesRead += cs.chunkSize

        m.thawFromStream(cs.read)
        self.failUnless(m.hasCompleteHeader())

        self.failIf(m.hasCompletePayload())

        # Same reason for not starting with 0 as above
        bytesRead = 0
        while bytesRead < len(testPayload1) - cs.chunkSize:
            m.thawFromStream(cs.read)
            self.failIf(m.hasCompletePayload())
            bytesRead += cs.chunkSize

        m.thawFromStream(cs.read)
        self.failUnless(m.hasCompletePayload())


    def testMessageContentType(self):
        m = envelope.Envelope()
        m.setContentType("text/foobared")

        stream = StringIO.StringIO()
        m.freezeToStream(stream.write)

        stream.seek(0)

        m.thawFromStream(stream.read)

        self.failUnlessEqual(m.getContentType(), "text/foobared")

    def testMessageWrite(self):
        m = envelope.Envelope()
        ct = "application/binary-stuff"
        m.setContentType(ct)

        line1 = "First line\n"
        line2 = "Second line\n"

        m.write(line1)
        m.write(line2)

        data = m.freeze()
        self.failUnlessEqual(data, testFrozenMessage2)
        self.failUnlessEqual(m.getContentType(), ct)

    def testMessageSeekTell(self):
        m = envelope.Envelope()
        ct = "application/binary-stuff"
        m.setContentType(ct)

        line1 = "First line\n"
        line2 = "Second line\n"

        m.write(line1)
        self.failUnlessEqual(m.tell(), len(line1))

        m.write(line2)
        self.failUnlessEqual(m.tell(), len(line1) + len(line2))

        m.seek(0)
        self.failUnlessEqual(m.tell(), 0)

        m.seek(0, 2)
        self.failUnlessEqual(m.tell(), len(line1) + len(line2))

        m.seek(0)
        m.write(line2)
        self.failUnlessEqual(m.tell(), len(line2))

        # Truncate up to 15 bytes
        m.truncate(15)
        self.failUnlessEqual(m.tell(), 15)

        # Seek to 10
        m.seek(10)
        m.truncate()
        self.failUnlessEqual(m.tell(), 10)

    def testSlowMessageRead(self):
        m = envelope.Envelope()
        ct = "application/binary-stuff"
        m.setContentType(ct)

        line1 = "First line\n"
        line2 = "Second line\n"
        m.write(line1)
        m.write(line2)
        data = m.freeze()
        # read in bytes one at a time.
        m = envelope.Envelope()
        for i in range(0, len(data)):
            stream = StringIO.StringIO()
            stream.write(data[i])
            stream.seek(0)
            complete = m.thawFromStream(stream.read)
            if complete:
                break
        assert(i == (len(data) - 1))
        assert(complete)
        assert(m.freeze() == data)

    def testSlowMessageWrite(self):
        m = envelope.Envelope()
        ct = "application/binary-stuff"
        m.setContentType(ct)

        line1 = "First line\n"
        line2 = "Second line\n"
        m.write(line1)
        m.write(line2)
        data = m.freeze()

        outStream = StringIO.StringIO()
        def writeone(data):
            outStream.write(data[0])
            return 1
        for i in range(0, len(data)):
            complete = m.freezeToStream(writeone)
            if complete:
                break
        assert(complete)
        outStream.seek(0)
        assert(outStream.read() == data)

    def testWriteMessageToTwoSources(self):
        # We need to be able to write the same message
        # to two sources simultaneously.
        # Having a writer object gives us a separate marker
        # into the payload stream, etc.
        m = envelope.Envelope()
        ct = "application/binary-stuff"
        m.setContentType(ct)

        line1 = "First line\n"
        line2 = "Second line\n"
        m.write(line1)
        m.write(line2)
        writer1 = m.getWriter()
        writer2 = m.getWriter()
        data = m.freeze()

        outStream1 = StringIO.StringIO()
        outStream2 = StringIO.StringIO()
        def writeone(data):
            outStream1.write(data[0])
            return 1
        def writeone2(data):
            outStream2.write(data[0])
            return 1

        writer1Complete = False
        writer2Complete = False
        while not writer1Complete and not writer2Complete:
            writer1Complete = writer1(writeone)
            writer2Complete = writer2(writeone2)
        outStream1.seek(0)
        assert(outStream1.read() == data)
        outStream2.seek(0)
        assert(outStream2.read() == data)
