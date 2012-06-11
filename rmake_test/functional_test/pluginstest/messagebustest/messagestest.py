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
