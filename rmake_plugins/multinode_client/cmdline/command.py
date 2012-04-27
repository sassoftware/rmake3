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
