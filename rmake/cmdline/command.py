import sys

from conary import conarycfg
from conary.deps import deps
from conary.lib import log
from conary.lib import options

from rmake import compat, errors
from rmake.build import buildcfg
from rmake.cmdline import query
from rmake.lib import flavorutil


(NO_PARAM,  ONE_PARAM)  = (options.NO_PARAM, options.ONE_PARAM)
(OPT_PARAM, MULT_PARAM) = (options.OPT_PARAM, options.MULT_PARAM)
(NORMAL_HELP, VERBOSE_HELP)  = (options.NORMAL_HELP, options.VERBOSE_HELP)

CG_MISC = 'Miscellaneous Commands'
CG_BUILD = 'Job Manipulation'
CG_INFO = 'Information Display'

# helper function to get list of commands we support
_commands = []
def register(cmd):
    _commands.append(cmd)

class rMakeCommand(options.AbstractCommand):
    defaultGroup = 'Common Options'
    commandGroup = CG_MISC

    docs = {'config'             : (VERBOSE_HELP,
                                    "Set config KEY to VALUE", "'KEY VALUE'"),
            'server-config'      : (VERBOSE_HELP,
                            "Set server config KEY to VALUE", "'KEY VALUE'"),
            'config-file'        : (VERBOSE_HELP,
                                    "Read PATH config file", "PATH"),
            'context'            : (VERBOSE_HELP,
                                    "Set the configuration context to use"),
            'server-config-file' : (VERBOSE_HELP,
                                    "Read PATH config file", "PATH"),
            'conary-config-file'  : (VERBOSE_HELP,
                                    "Read PATH conary config file", "PATH"),
            'build-config-file'  : (VERBOSE_HELP,
                                    "Read PATH config file", "PATH"),
            'rmake-config-file'  : (VERBOSE_HELP,
                                    "Read PATH config file", "PATH"),
            'skip-default-config': (VERBOSE_HELP,
                                    "Don't read default configs"),
           }

    def addParameters(self, argDef):
        d = {}
        d["context"] = ONE_PARAM
        d["config"] = MULT_PARAM
        d["server-config"] = MULT_PARAM
        d["server-config-file"] = MULT_PARAM
        d["build-config-file"] = MULT_PARAM
        d["conary-config-file"] = MULT_PARAM
        d["skip-default-config"] = NO_PARAM
        argDef[self.defaultGroup] = d

    def processConfigOptions(self, (buildConfig, serverConfig, conaryConfig,
                                    pluginManager), cfgMap, argSet):
        """
            Manage any config maps we've set up, converting 
            assigning them to the config object.
        """ 
        configFileList = argSet.pop('build-config-file', [])
        if not isinstance(configFileList, list):
            configFileList = list(configFileList)

        configFileList.extend(argSet.pop('config-file', []))

        for path in configFileList:
            buildConfig.read(path, exception=True)


        configFileList = argSet.pop('server-config-file', [])
        if not isinstance(configFileList, list):
            configFileList = list(configFileList)
        for path in configFileList:
            serverConfig.read(path, exception=True)

        configFileList = argSet.pop('conary-config-file', [])
        if not isinstance(configFileList, list):
            configFileList = list(configFileList)
        if configFileList and not conaryConfig:
            conaryConfig = conarycfg.ConaryConfiguration(readConfigFiles=False)
        for path in configFileList:
            conaryConfig.read(path, exception=True)

        for (arg, data) in cfgMap.items():
            cfgName, paramType = data[0:2]
            value = argSet.pop(arg, None)
            if value is not None:
                if arg.startswith('no-'):
                    value = not value

                buildConfig.configLine("%s %s" % (cfgName, value))

        for line in argSet.pop('config', []):
            buildConfig.configLine(line)

        for line in argSet.pop('server-config', []):
            serverConfig.configLine(line)

    def requireParameters(self, args, expected=None, allowExtra=False,
                          appendExtra=False, maxExtra=None):
        args = args[1:] # cut off argv[0]
        command = repr(args[0])
        if isinstance(expected, str):
            expected = [expected]
        if expected is None:
            expected = ['command']
        else:
            expected = ['command'] + expected
        if expected:
            missing = expected[len(args):]
            if missing:
                raise errors.BadParameters('%s missing %s command'
                                           ' parameter(s): %s' % (
                                            command, len(missing),
                                            ', '.join(missing)))
        extra = len(args) - len(expected)
        if not allowExtra and not appendExtra:
            maxExtra = 0
        if maxExtra is not None and extra > maxExtra:
            if maxExtra:
                numParams = '%s-%s' % (len(expected)-1,
                                       len(expected) + maxExtra - 1)
            else:
                 numParams = '%s' % (len(expected)-1)
            raise errors.BadParameters('%s takes %s arguments, received %s' % (command, numParams, len(args)-1))

        if appendExtra:
            # final parameter is list 
            return args[:len(expected)-1] + [args[len(expected)-1:]]
        elif allowExtra:
            return args[:len(expected)] + [args[len(expected):]]
        else:
            return args


def _getJobIdOrUUIds(val):
    return [ _getJobIdOrUUId(x) for x in val ]

def _getJobIdOrUUId(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        if isinstance(val, str) and len(val) == 32:
            return val
        else:
            raise errors.ParseError, 'Not a valid jobId or UUID: %s' % val

class BuildCommand(rMakeCommand):
    '''Builds the specified packages or recipes.  '''

    commands = ['build', 'buildgroup']
    commandGroup = CG_BUILD
    paramHelp = '<troveSpec>[{context}] [<troveSpec>][{context}]*'
    help = 'Build packages or recipes'

    docs = {'flavor' : "flavor to build with",
            'host'   : "host to limit build to",
            'label'  : "label to limit build to",
            'match'  : (options.VERBOSE_HELP, 
                        "Only build troves that match the given specification"),
            'no-watch'  : "do not show build status",
            'poll'   : (options.VERBOSE_HELP, 'backwards compatibility option'),
            'quiet'  : "show less build info - don't tail logs",
            'commit' : "commit job when it is done",
            'macro'   : ('set macro NAME to VALUE', "'NAME VALUE'"),
            'no-clean': 'do not remove build directory even if build is'
                        ' successful',
            'binary-search': (options.VERBOSE_HELP,
                              'Search for the binary'
                              'version of group and build the latest'
                              'sources on that branch with the same flavor'),
            'reuse':    ('reuse old chroot if possible instead of removing'
                         ' and recreating'),
            'recurse':  ('recurse groups, building all included sources')}

    def addParameters(self, argDef):
        argDef['flavor'] = ONE_PARAM
        argDef['host'] = MULT_PARAM
        argDef['label'] = MULT_PARAM
        argDef['quiet'] = NO_PARAM
        argDef['commit'] = NO_PARAM
        argDef['macro'] = MULT_PARAM
        argDef['match'] = MULT_PARAM
        argDef['no-watch'] = NO_PARAM
        argDef['poll'] = NO_PARAM
        argDef['binary-search'] = NO_PARAM
        argDef['recurse'] = NO_PARAM
        argDef['no-clean'] = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def addConfigOptions(self, cfgMap, argDef):
        cfgMap['reuse'] = 'reuseRoots', NO_PARAM
        rMakeCommand.addConfigOptions(self, cfgMap, argDef)


    def runCommand(self, client, cfg, argSet, args):
        log.setVerbosity(log.INFO)
        command, troveSpecs = self.requireParameters(args, 'troveSpec',
                                                     appendExtra=True)
        flavorSpec = argSet.pop('flavor', None)
        if flavorSpec:
            flavor = deps.parseFlavor(flavorSpec)
            if flavor is None:
                raise errors.ParseError("Invalid flavor: '%s'" % flavorSpec)
            newFlavor = deps.overrideFlavor(client.buildConfig.buildFlavor, 
                                            flavor)
            client.buildConfig.buildFlavor = newFlavor
            newFlavors = []
            for oldFlavor in client.buildConfig.flavor:
                newFlavors.append(deps.overrideFlavor(oldFlavor, flavor))
            client.buildConfig.flavor = newFlavors

        matchSpecs = argSet.pop('match', [])

        if 'no-clean' in argSet:
            client.buildConfig.cleanAfterCook = False
            del argSet['no-clean']

        macros = argSet.pop('macro', [])
        for macro in macros:
            client.buildConfig.configLine('macros ' + macro)

        hosts = argSet.pop('host', [])
        labels = argSet.pop('label', [])
        quiet = argSet.pop('quiet', False)
        commit  = argSet.pop('commit', False)
        recurseGroups = argSet.pop('recurse', False) or command == 'buildgroup'

        if recurseGroups:
            if argSet.pop('binary-search', False):
                recurseGroups = client.BUILD_RECURSE_GROUPS_BINARY
            elif not compat.ConaryVersion().supportsFindGroupSources():
                log.warning('Your conary does not support recursing a group'
                            ' source component, defaulting to searching the'
                            ' binary version')
                recurseGroups = client.BUILD_RECURSE_GROUPS_BINARY
            else:
                recurseGroups = client.BUILD_RECURSE_GROUPS_SOURCE
        monitorJob = not argSet.pop('no-watch', False)

        jobId = client.buildTroves(troveSpecs,
                                   limitToHosts=hosts, limitToLabels=labels,
                                   recurseGroups=recurseGroups,
                                   matchSpecs=matchSpecs,
                                   quiet=quiet)
        if quiet:
            print jobId
        if monitorJob:
            if quiet:
                if not client.waitForJob(jobId):
                    return 1
            elif not client.watch(jobId, showTroveLogs=not quiet,
                               showBuildLogs=not quiet,
                               commit=commit):
                return 1
        elif commit:
            if not client.commitJob(jobId, commitWithFailures=False,
                                    waitForJob=True):
                return 1
        return 0

register(BuildCommand)

class RestartCommand(BuildCommand):
    '''Rebuilds the specified job'''

    commands = ['restart']
    commandGroup = CG_BUILD
    paramHelp = '<jobId> [<troveSpec>]*'
    help = 'Rebuild an earlier job'

    def addParameters(self, argDef):
        argDef['commit'] = NO_PARAM
        argDef['no-watch'] = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def runCommand(self, client, cfg, argSet, args):
        log.setVerbosity(log.INFO)
        command, jobId, troveSpecs = self.requireParameters(args, 'jobId', 
                                                            allowExtra=True)
        jobId = _getJobIdOrUUId(jobId)

        commit  = argSet.pop('commit', False)
        jobId = client.restartJob(jobId, troveSpecs)
        monitorJob = not argSet.pop('no-watch', False)
        if monitorJob:
            if not client.watch(jobId, commit=commit,
                                showTroveLogs=True,
                                showBuildLogs=True):
                return 1
        elif commit:
            if not client.commitJob(jobId, commitWithFailures=False,
                                    waitForJob=True):
                return 1
        return 0
register(RestartCommand)

class ChangeSetCommand(rMakeCommand):
    commands = ['changeset']
    hidden = True
    paramHelp = '''\
<jobId> <troveSpec>* <outfile>

Creates a changeset with the troves from the job <jobId> and stores in outFile'
'''
    help = 'Create a changeset file from the packages in a job'

    def runCommand(self, client, cfg, argSet, args):
        command, jobId, path = self.requireParameters(args, ['jobId', 'path'],
                                                        appendExtra=True)
        if len(path) > 1:
            troveSpecs = path[:-1]
            path = path[-1]
        else:
            troveSpecs = []
            path = path[0]
        jobId = _getJobIdOrUUId(jobId)
        client.createChangeSetFile(jobId, path, troveSpecs)
register(ChangeSetCommand)

class CommitCommand(rMakeCommand):
    commands = ['commit', 'ci']
    commandGroup = CG_BUILD
    paramHelp = '''<jobId> [<jobId>]

Commits the build packages from the jobs, moving them from rMake's internal 
repository back into the repository where their source package came from.
'''
    help = 'Commit a job'

    docs = {'commit-outdated-sources' : ("Allow commits of source components when another"
                                         " commit has been made upstream"),
            'source-only'             : "Only commit the source changes" }

    def addParameters(self, argDef):
        argDef['source-only'] = NO_PARAM
        argDef['commit-outdated-sources'] = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def runCommand(self, client, cfg, argSet, args):
        command, jobIds = self.requireParameters(args, ['jobId'],
                                                 appendExtra=True)
        commitOutdated = argSet.pop('commit-outdated-sources', False)
        sourceOnly = argSet.pop('source-only', False)
        jobIds = _getJobIdOrUUIds(jobIds)
        success = client.commitJobs(jobIds,
                                    commitOutdatedSources=commitOutdated,
                                    commitWithFailures=True, waitForJob=True,
                                    sourceOnly=sourceOnly)
        if success:
            return 0
        else:
            return 1

register(CommitCommand)

class ConfigCommand(rMakeCommand):
    commands = ['config']
    commandGroup = CG_INFO
    help = 'Display the current configuration'
    docs = {'show-passwords' : 'do not mask passwords'}

    def addParameters(self, argDef):
         rMakeCommand.addParameters(self, argDef)
         argDef["show-passwords"] = NO_PARAM

    def runCommand(self, client, cfg, argSet, args):
        self.requireParameters(args)

        showPasswords = argSet.pop('show-passwords', False)
        try:
            prettyPrint = sys.stdout.isatty()
        except AttributeError:
            prettyPrint = False
        client.displayConfig(hidePasswords=not showPasswords,
                             prettyPrint=prettyPrint)
register(ConfigCommand)

class DeleteCommand(rMakeCommand):
    commands = ['delete']
    commandGroup = CG_BUILD
    paramHelp = '<jobId>[-<jobId>]+'
    help = 'Delete jobs from rmake\'s history'

    def runCommand(self, client, cfg, argSet, args):
        toDelete = []
        command, jobList = self.requireParameters(args, 'jobId',
                                                  appendExtra=True)
        for arg in jobList:
            values = arg.split(',')
            for value in values:
                range = value.split('-', 1)
                if len(range) == 1:
                    toDelete.append(_getJobIdOrUUId(value))
                else:
                    fromVal = _getJobIdOrUUId(range[0])
                    toVal = _getJobIdOrUUId(range[1])
                    if (not isinstance(fromVal, int) 
                        or not isinstance(toVal, int)):
                        raise ParseError('Must use jobIds when specifying'
                                         ' range to delete')
                    toDelete.extend(xrange(fromVal, toVal + 1))
        client.deleteJobs(toDelete)
register(DeleteCommand)

class HelpCommand(rMakeCommand):
    commands = ['help']
    help = 'Display help information'
    commandGroup = CG_INFO

    def runCommand(self, client, cfg, argSet, args):
        command, subCommands = self.requireParameters(args, allowExtra=True,
                                                      maxExtra=1)
        if subCommands:
            command = subCommands[0]
            commands = self.mainHandler._supportedCommands
            if not command in commands:
                print "%s: no such command: '%s'" % (self.mainHandler.name,
                                                     command)
                sys.exit(1)
            commands[command].usage()
        else:
            self.mainHandler.usage(showAll=True)
            return 0
register(HelpCommand)


class PollCommand(rMakeCommand):
    commands = ['poll', 'watch']
    commandGroup = CG_INFO
    paramHelp = '''<jobId>

Watch the progress of job <jobId> as it builds its packages
'''
    help = 'Watch a job build'

    docs = { 'quiet'  : 'Only display major job status changes',
             'commit' : "Commit job when it is done"}

    def addParameters(self, argDef):
        rMakeCommand.addParameters(self, argDef)
        argDef['quiet'] = NO_PARAM
        argDef['commit'] = NO_PARAM

    def runCommand(self, client, cfg, argSet, args):
        command, jobId = self.requireParameters(args, 'jobId')
        log.setVerbosity(log.INFO)
        quiet = argSet.pop('quiet', False)
        commit = argSet.pop('commit', False)
        jobId = _getJobIdOrUUId(jobId)
        success = client.watch(jobId, showBuildLogs = not quiet,
                               showTroveLogs = not quiet,
                               commit = commit)
        if success:
            return 0
        else:
            return 1
register(PollCommand)

class StopCommand(rMakeCommand):
    commands = ['stop']
    commandGroup = CG_BUILD
    help = 'Stop job from building'
    paramHelp = '''<jobId>

Stops job <jobId> from building.
'''

    def runCommand(self, client, cfg, argSet, args):
        command, jobId = self.requireParameters(args, 'jobId')
        log.setVerbosity(log.INFO)
        jobId = _getJobIdOrUUId(jobId)
        client.stopJob(jobId)
register(StopCommand)

class QueryCommand(rMakeCommand):
    commands = ['query', 'q']
    commandGroup = CG_INFO
    help = 'Display information about a job'
    paramHelp = '''[<jobId> <troveSpec>*]

    Display information about the job <jobId> (limited to <troveSpec> 
    if specified)
'''

    docs = {'troves'          : 'Display troves for this job',
            'info'            : 'Display details',
            'logs'            : 'Display logs associated with jobs/troves',
            'watch'            : 'Continually update status while job builds',
            'full-versions'   : 'Show full versions',
            'labels'          : 'Show labels',
            'flavors'         : 'Show full flavors',
            'tracebacks'      : 'Show tracebacks'
           }


    def addParameters(self, argDef):
        argDef['troves'] = NO_PARAM
        argDef['info'] = NO_PARAM
        argDef['tracebacks'] = NO_PARAM
        argDef['full-versions'] = NO_PARAM
        argDef['labels']     = NO_PARAM
        argDef['flavors']    = NO_PARAM
        argDef['logs']       = NO_PARAM
        argDef['watch']       = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def runCommand(self, client, cfg, argSet, args):
        command, args = self.requireParameters(args, allowExtra=True)
        if args:
            jobId = _getJobIdOrUUId(args[0])
            troveSpecs = args[1:]
            try:
                jobId = int(jobId)
            except ValueError:
                self.usage()
                log.error("bad jobId '%s'", jobId)
                return 1
        else:
            jobId = None
            troveSpecs = []
        displayTroves  = argSet.pop('troves', False)
        displayDetails = argSet.pop('info', False)
        showFullVersions = argSet.pop('full-versions', False)
        showFullFlavors = argSet.pop('flavors', False)
        showLabels = argSet.pop('labels', False)
        showTracebacks = argSet.pop('tracebacks', False)
        showLogs       = argSet.pop('logs', False)
        watchJob       = argSet.pop('watch', False)
        query.displayJobInfo(client, jobId, troveSpecs,
                                    displayTroves=displayTroves,
                                    displayDetails=displayDetails,
                                    showLogs=showLogs,
                                    showBuildLogs=showLogs,
                                    showFullVersions=showFullVersions,
                                    showFullFlavors=showFullFlavors,
                                    showLabels=showLabels,
                                    showTracebacks=showTracebacks)
        if watchJob:
            client.watch(jobId, showBuildLogs = True, showTroveLogs = True)

register(QueryCommand)



class ListCommand(rMakeCommand):
    """\
    List information about the given rmake server.

    Types Available:
        list [ch]roots - lists chroots on this rmake server"""
    commands = ['list']
    paramHelp = "<type>"
    help = 'List various information about this rmake server'
    commandGroup = CG_INFO

    docs = {'all' : 'Backwards compatibility option',
            'active' : 'Display only active items' }

    def addParameters(self, argDef):
        argDef['all'] = NO_PARAM
        argDef['active'] = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def runCommand(self, client, cfg, argSet, args):
        command, subCommand = self.requireParameters(args, 'command')
        commandFn = getattr(self, 'list%s' % subCommand.title(), None)
        if not commandFn:
            self.usage()
            raise errors.RmakeError('No such list command %s' % subCommand)
        commandFn(client, cfg, argSet)


    def listChroots(self, client, cfg, argSet):
        allChroots = not argSet.pop('active', False)
        query.listChroots(client, cfg, allChroots=allChroots)
    listRoots = listChroots
register(ListCommand)

class ChrootCommand(rMakeCommand):
    """\
    Runs /bin/sh in the given chroot.

    This command allows you to debug problems that occur with a build in
    rMake.  By default, it enters the chroot as the user who built the
    trove.  With the --super parameter you can cause it to run as the 
    "rmake" user, who can then run commands like "conary update strace."\
"""
    help = 'Run /bin/sh in a given chroot'
    paramHelp = "<chrootName>"

    commands = ['chroot']

    docs = {'super' :
             'Run as a user capable of modifying the contents of the root' }

    def addParameters(self, argDef):
        argDef['super'] = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def _getChroot(self, chroot):
        return '_local_', chroot

    def runCommand(self, client, cfg, argSet, args):
        command, chroot = self.requireParameters(args, ['chrootPath'])
        host, chroot = self._getChroot(chroot)
        superUser = argSet.pop('super', False)
        client.startChrootSession(host, chroot, ['/bin/bash', '-l'],
                                  superUser=superUser)
register(ChrootCommand)

class ArchiveCommand(rMakeCommand):
    """\
    Archive a chroot so that it will not be overwritten by rmake during the
    build process.

    By default, rmake will reuse particular names for chroots
    whenever building something with that same name.  This command can be used
    to safely move a chroot out of the way for further debugging without 
    requiring that normal rmake use be stopped."""
    commands = ['archive']
    paramHelp = '<chrootName> <newName>'
    help = 'Archives a chroot for later use'

    def addParameters(self, argDef):
        rMakeCommand.addParameters(self, argDef)

    def _getChroot(self, chroot):
        return '_local_', chroot

    def runCommand(self, client, cfg, argSet, args):
        command, chroot, extra = self.requireParameters(args,
                                                       ['chrootPath'],
                                                        allowExtra=1)
        host, chroot = self._getChroot(chroot)
        if extra:
            newPath = extra[0]
        else:
            newPath = chroot
        client.archiveChroot(host, chroot, newPath)
register(ArchiveCommand)


class CleanCommand(rMakeCommand):
    """\
    Removes the given chroot, freeing its space.

    This command simply removes the given chroot and everything within it,
    freeing its diskspace.

    Specifying --all means remove all old chroots.
    """
    commands = ['clean']
    help = 'Deletes a chroot'
    paramHelp = '<chroot>'

    def addParameters(self, argDef):
        argDef['all'] = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def _getChroot(self, chroot):
        return '_local_', chroot

    def runCommand(self, client, cfg, argSet, args):
        if argSet.pop('all', False):
            client.deleteAllChroots()
        else:
            command, chroot  = self.requireParameters(args, ['chrootPath'])
            client.deleteChroot(*self._getChroot(chroot))
register(CleanCommand)


def addCommands(main):
    for command in _commands:
        main._registerCommand(command)


