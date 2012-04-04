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
