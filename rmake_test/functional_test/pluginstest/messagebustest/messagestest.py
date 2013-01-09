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
