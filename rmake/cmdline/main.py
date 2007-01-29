#!/usr/bin/python2.4
#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
Simple client that communicates with rMake.
"""

import errno
import os
import sys


from conary import conarycfg
from conary import errors as conaryerrors
from conary.lib import cfg, log
from conary.lib import options

from rmake import constants
from rmake import errors


sys.excepthook = errors.genExcepthook()

from rmake import compat
from rmake import plugins

from rmake.build import buildcfg
from rmake.cmdline import command
from rmake.cmdline import helper
from rmake.server import servercfg


class RmakeMain(options.MainHandler):
    name = 'rmake'
    version = constants.version

    abstractCommand = command.rMakeCommand
    configClass = buildcfg.BuildConfiguration

    commandList = command._commands

    def usage(self, rc=1, showAll=False):
        print 'rmake: front end to rMake build tool'
        if not showAll:
            print
            print 'Common Commands (use "rmake help" for the full list)'
        return options.MainHandler.usage(self, rc, showAll=showAll)

    def initializePlugins(self, argv):
        p = plugins.getPluginManager(argv, buildcfg.BuildConfiguration)
        p.callClientHook('client_preInit', self, argv)
        return p

    def getConfigFile(self, argv):
        pluginManager = self.initializePlugins(argv)
        if '--skip-default-config' in argv:
            argv.remove('--skip-default-config')
            read = False
        else:
            read = True

        serverConfig = servercfg.rMakeConfiguration(readConfigFiles=read)
        buildConfig = buildcfg.BuildConfiguration(readConfigFiles=read)
        conaryConfig = conarycfg.ConaryConfiguration(readConfigFiles=read)
        return buildConfig, serverConfig, conaryConfig, pluginManager

    def _getContext(self, buildConfig, conaryConfig, argSet):
        context = conaryConfig.context
        if buildConfig.context:
            context = buildConfig.context
        if os.path.exists('CONARY'):
            conaryState = compat.ConaryVersion().ConaryStateFromFile('CONARY',
                                                           parseSource=False)
            if conaryState.hasContext():
                context = conaryState.getContext()

        context = os.environ.get('CONARY_CONTEXT', context)
        context = argSet.get('context', context)
        return context

    def runCommand(self, thisCommand, (buildConfig, serverConfig, conaryConfig,
                                       pluginManager), argSet, args):
        pluginManager.callClientHook('client_preCommand', self, thisCommand,
                                     (buildConfig, serverConfig, conaryConfig),
                                     argSet, args)
        compat.checkRequiredVersions()
        thisCommand.verbose = (log.getVerbosity() <= log.INFO)
        if args[1] != 'help':
            # NOTE: the help system assumes that the base level of output
            # you want is "warning", but rmake is more verbose than that.
            # Due to limitations in how configurable the help system is, 
            # I can't easily fix that.  Someday I should though.  For now,
            # if we're running help, we make log.WARNING the default level,
            # and otherwise log.INFO is the default.
            log.setMinVerbosity(log.INFO)
        context = self._getContext(buildConfig, conaryConfig, argSet)
        if conaryConfig and context:
            conaryConfig.setContext(context)


        buildConfig.useConaryConfig(conaryConfig)
        if context:
            buildConfig.setContext(context)

        buildConfig.initializeFlavors()

        client = helper.rMakeHelper(buildConfig=buildConfig,
                                    rmakeConfig=serverConfig)

        pluginManager.callClientHook('client_preCommand2', self, client,
                                     thisCommand)

        try:
            return options.MainHandler.runCommand(self, thisCommand, client, 
                                                  buildConfig, argSet, args)
        except errors.BadParameters:
            if not thisCommand.verbose:
                log.setVerbosity(log.WARNING)
            thisCommand.usage()
            raise

def main(argv):
    log.setVerbosity(log.WARNING)
    rmakeMain = RmakeMain()
    try:
        argv = list(argv)
        debugAll = '--debug-all' in argv
        if debugAll:
            debuggerException = Exception
            argv.remove('--debug-all')
        else:
            debuggerException = errors.RmakeInternalError
        sys.excepthook = errors.genExcepthook(debug=debugAll,
                                              debugCtrlC=debugAll)
        compat.ConaryVersion().checkRequiredVersion()
        return RmakeMain().main(argv, debuggerException=debuggerException)
    except debuggerException, err:
        raise
    except errors.OpenError, err:
        log.error(str(err) + ' -- check to see that the server is running.')
    except (errors.RmakeError, conaryerrors.ConaryError, cfg.ParseError,
            conaryerrors.CvcError), err:
        log.error(err)
        return 1
    except IOError, e:
        # allow broken pipe to exit
        if e.errno != errno.EPIPE:
            raise
    except KeyboardInterrupt:
        pass
    return 0
