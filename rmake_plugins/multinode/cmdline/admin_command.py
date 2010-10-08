#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import sys
from rmake_plugins.multinode import admin
from rmake.lib import daemon

_commands = []
def register(cmd):
    _commands.append(cmd)


class AdminCommand(daemon.DaemonCommand):

    def _getAdminClient(self, cfg):
        return admin.getAdminClient(cfg.getMessageBusHost(), cfg.messageBusPort)


class StatusCommand(AdminCommand):
    """
        Give status information about internal rMake pieces

        Example:
            status dispatcher - displays current state of dispatcher
            status node <nodeId> - displays current state of node
            status messagebus - displays current status of messagebus

        These commands are used mostly for debugging
    """
    commands = ['status']
    help = 'List various internal state for this rmake server'

    def runCommand(self, daemon, cfg, argSet, args):
        adminClient = self._getAdminClient(cfg)
        command, subCommand, extra = self.requireParameters(args, 'server',
                                                            allowExtra=True)
        if subCommand == 'messagebus':
            print "Connected clients: Messages Queued"
            queueLens = adminClient.listMessageBusQueueLengths()
            for sessionId in sorted(adminClient.listMessageBusClients()):
                print '%s: %s' % (sessionId, queueLens[sessionId])
        if subCommand == 'dispatcher':
            print "Nodes:"
            print '\n'.join(adminClient.listNodes())
            print "Queued commands:"
            print '\n'.join(adminClient.listQueuedCommands())
            print "Assigned commands:"
            for command, nodeId in adminClient.listAssignedCommands():
                print "%s: %s" % (command, nodeId)
        if subCommand == 'node':
            subCommand, nodeId = self.requireParameters(args[1:], 'nodeId')
            print "Node %s" % nodeId
            (queued, active) = adminClient.listNodeCommands(nodeId)
            if queued:
                print " Queued Commands: "
                for command in queued:
                    print "   %s" % command
            if active:
                print " Active Commands: "
                for command, pid in active:
                    print "   %s (pid %s)" % (command, pid)
            if not (queued or active):
                print " (No commands running)"
register(StatusCommand)


class SuspendCommand(AdminCommand):
    commands = ['suspend']
    help = "Suspend a node from receiving further jobs."

    _suspend = True

    def runCommand(self, daemon, cfg, argSet, args):
        if len(args) < 3:
            sys.exit("Expected one or more node session IDs")
        adminClient = self._getAdminClient(cfg)
        adminClient.suspendNodes(args[2:], suspend=self._suspend)
        action = self._suspend and 'Suspended' or 'Resumed'
        print "%s %d node(s)" % (action, len(args) - 2)
register(SuspendCommand)


class ResumeCommand(SuspendCommand):
    commands = ['resume']
    help = "Resume a node for receiving further jobs."
    _suspend = False
register(ResumeCommand)


def addCommands(main):
    for command in _commands:
        main._registerCommand(command)
