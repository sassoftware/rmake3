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

