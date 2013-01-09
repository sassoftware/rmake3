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
from testutils import mock

from rmake.cmdline import command
from rmake import constants


class CommandTest(rmakehelp.RmakeHelper):
    def testBuildImageCommand(self):
        cmd = command.BuildImageCommand()
        mock.mockMethod(cmd._build)
        client = mock.MockObject()
        cfg = mock.MockObject()
        cmd.runCommand(client, cfg,
                       {'option': ['imageOption=foo', 'blah=bar']},
                       ['rmake', 'buildimage', 'project',
                        'group-foo', 'imageType'])
        client.createImageJob._mock.assertCalled('project',
                                                 [('group-foo', 'imageType',
                                                   {'imageOption': 'foo',
                                                    'blah': 'bar'})])
        job = client.createImageJob()
        cmd._build._mock.assertCalled(client, job, {})

    def testVersion(self):
        assert(constants.version)
        assert(constants.changeset)
