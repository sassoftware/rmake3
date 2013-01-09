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


from rmake import errors

from rmake.cmdline import command
from rmake.cmdline import query

_commands = []
def register(cmd):
    _commands.append(cmd)

class ListCommand(command.ListCommand):
    """
        List information about the given rmake server.

        Example:
            list roots  - lists roots associated with this server
            list nodes  - lists nodes attached to this rmake server
    """
    commands = ['list']
    help = 'List various information about this rmake server'
    commandGroup = command.CG_INFO

    def listNodes(self, client, cfg, argSet):
        for node in client.client.listNodes():
            buildFlavors = ', '.join(['[%s]' % x for x in node.flavors])
            if node.slots > 1:
                print '%s %s (%s slots)' % (node.name, buildFlavors, node.slots)
            else:
                print '%s %s (1 slot)' % (node.name, buildFlavors)
            for chroot in node.chroots:
                if chroot.active:
                    query.displayChroot(chroot)

register(ListCommand)

class RemoteChrootMixin:
    # override chroot command to support node selection.
    def _getChroot(self, chroot):
        params = chroot.split(':', 1)
        if len(params) != 2:
            self.usage()
            raise errors.RmakeError(
                            'Chroot name needs to be <host>:<chroot> format')
        return params

class ChrootCommand(RemoteChrootMixin, command.ChrootCommand):
    pass
register(ChrootCommand)

class CleanCommand(RemoteChrootMixin, command.CleanCommand):
    pass
register(CleanCommand)

class ArchiveCommand(RemoteChrootMixin, command.ArchiveCommand):
    pass
register(ArchiveCommand)

def addCommands(main):
    for command in _commands:
        main._registerCommand(command)
