import os
import sys

from conary import conarycfg
from conary import cvc
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
            'verbose'            : (VERBOSE_HELP,
                                    "Display more detailed information where available") }

    def addParameters(self, argDef):
        d = {}
        d["context"] = ONE_PARAM
        d["config"] = MULT_PARAM
        d["server-config"] = MULT_PARAM
        d["server-config-file"] = MULT_PARAM
        d["build-config-file"] = MULT_PARAM
        d["conary-config-file"] = MULT_PARAM
        d["skip-default-config"] = NO_PARAM
        d["verbose"] = NO_PARAM
        argDef[self.defaultGroup] = d

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
        context = argSet.pop('context', context)
        return context

    def _setContext(self, buildConfig, conaryConfig, argSet):
        context = self._getContext(buildConfig, conaryConfig, argSet)
        usedContext = False
        if conaryConfig and context:
            if conaryConfig.hasSection(context):
                usedContext = True
                conaryConfig.setContext(context)

        buildConfig.useConaryConfig(conaryConfig)
        if context and buildConfig.hasSection(context):
            buildConfig.setContext(context)
            usedContext = True
        if not usedContext and context:
            raise errors.RmakeError('No such context "%s"' % context)

    def processConfigOptions(self, (buildConfig, conaryConfig, pluginManager), 
                             cfgMap, argSet):
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

        configFileList = argSet.pop('conary-config-file', [])
        if not isinstance(configFileList, list):
            configFileList = list(configFileList)
        if configFileList and not conaryConfig:
            conaryConfig = conarycfg.ConaryConfiguration(readConfigFiles=False)
        for path in configFileList:
            conaryConfig.read(path, exception=True)
        self._setContext(buildConfig, conaryConfig, argSet)

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
        if argSet.pop('verbose', False):
            log.setVerbosity(log.DEBUG)

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

    commands = ['build']
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
            'prep'   : (options.VERBOSE_HELP,
                            'do not build package, only create chroot'),
            'quiet'  : "show less build info - don't tail logs",
            'commit' : "commit job when it is done",
            'message' : "Message to assign to troves upon commit",
            'macro'   : ('set macro NAME to VALUE', "'NAME VALUE'"),
            'no-clean': 'do not remove build directory even if build is'
                        ' successful',
            'to-file': (options.VERBOSE_HELP,
                        'store job in a file instead of sending it'
                        ' to the server.  This makes it possible for others'
                        ' to start the job.'),
            'binary-search': (options.VERBOSE_HELP,
                              'Search for the binary'
                              'version of group and build the latest'
                              'sources on that branch with the same flavor'),
            'reuse':    ('reuse old chroot if possible instead of removing'
                         ' and recreating'),
            'info'    : ('Gather and display all the information necessary to perform the build'),
            'recurse':  ('recurse groups, building all included sources'),
            'ignore-rebuild-deps': ('Do not rebuild packages if the only'
                                    ' change to them is the packages to be'
                                    ' installed in their chroot.'),
            'ignore-external-rebuild-deps': ('Do not rebuild packages unless'
                                             ' their source has changed or'
                                             ' another package in the job will'
                                             ' be installed in this package\'s'
                                             ' chroot')}

    def addParameters(self, argDef):
        self.addBuildParameters(argDef)
        rMakeCommand.addParameters(self, argDef)
        argDef['flavor'] = ONE_PARAM
        argDef['host'] = MULT_PARAM
        argDef['label'] = MULT_PARAM
        argDef['match'] = MULT_PARAM
        argDef['binary-search'] = NO_PARAM
        argDef['recurse'] = NO_PARAM

    def addBuildParameters(self, argDef):
        argDef['commit'] = NO_PARAM
        argDef['prep'] = NO_PARAM
        argDef['macro'] = MULT_PARAM
        argDef['message'] = '-m', ONE_PARAM
        argDef['no-watch'] = NO_PARAM
        argDef['poll'] = NO_PARAM
        argDef['no-clean'] = NO_PARAM
        argDef['to-file'] = ONE_PARAM
        argDef['quiet'] = NO_PARAM
        argDef['info'] = NO_PARAM

    def addConfigOptions(self, cfgMap, argDef):
        cfgMap['reuse'] = 'reuseRoots', NO_PARAM
        rMakeCommand.addConfigOptions(self, cfgMap, argDef)

    def runCommand(self, client, cfg, argSet, args):
        if self.verbose:
            log.setVerbosity(log.DEBUG)
        else:
            log.setVerbosity(log.INFO)
        command, troveSpecs = self.requireParameters(args, 'troveSpec',
                                                     appendExtra=True)
        if command == 'buildgroup':
            log.warning('"buildgroup" is deprecated and will be removed in a future release - use "build --recurse" instead')
        rebuild = (command == 'rebuild')
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
        hosts = argSet.pop('host', [])
        labels = argSet.pop('label', [])
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

        self._prep(client, argSet)
        job = client.createBuildJob(troveSpecs, limitToHosts=hosts,
                                    limitToLabels=labels,
                                    recurseGroups=recurseGroups,
                                    matchSpecs=matchSpecs,
                                    rebuild=rebuild)
        return self._build(client, job, argSet)

    def _prep(self, client, argSet):
        if 'no-clean' in argSet:
            client.buildConfig.cleanAfterCook = False
            del argSet['no-clean']
        if 'prep' in argSet:
            client.buildConfig.prepOnly = argSet.pop('prep')
        if 'ignore-rebuild-deps' in argSet:
            client.buildConfig.ignoreAllRebuildDeps = True
            argSet.pop('ignore-rebuild-deps')
        if 'ignore-external-rebuild-deps' in argSet:
            client.buildConfig.ignoreExternalRebuildDeps = True
            argSet.pop('ignore-external-rebuild-deps')

        macros = argSet.pop('macro', [])
        for macro in macros:
            client.buildConfig.configLine('macros ' + macro)

        if 'no-clean' in argSet:
            client.buildConfig.cleanAfterCook = False
            del argSet['no-clean']


    def _build(self, client, job, argSet):
        savePath = argSet.pop('to-file', False)

        quiet = argSet.pop('quiet', False)
        commit  = argSet.pop('commit', False)
        message  = argSet.pop('message', None)
        infoOnly  = argSet.pop('info', False)
        monitorJob = not argSet.pop('no-watch', False)

        if infoOnly:
            client.displayJob(job, quiet=quiet)
        if savePath:
            job.writeToFile(savePath, sanitize=True)
        if infoOnly or savePath:
            return 0
        jobId = client.buildJob(job, quiet=quiet)
        if monitorJob:
            if quiet:
                if not client.waitForJob(jobId):
                    return 1
            elif not client.watch(jobId, showTroveLogs=not quiet,
                               showBuildLogs=not quiet,
                               commit=commit, message=message):
                return 1
        elif commit:
            if not client.commitJob(jobId, commitWithFailures=False,
                                    waitForJob=True, message=message):
                return 1
        return 0
register(BuildCommand)

class RebuildCommand(BuildCommand):
    '''\
        Rebuilds packages whose source or dependencies have changed.
    '''
    commands = ['rebuild']
    commandGroup = CG_BUILD
    paramHelp = '<troveSpec>[{context}] [<troveSpec>][{context}]*'
    help = 'Rebuild packages or recipes if they\'ve changed'

    def addParameters(self, argDef):
        BuildCommand.addParameters(self, argDef)
        argDef['ignore-rebuild-deps'] = NO_PARAM
        argDef['ignore-external-rebuild-deps'] = NO_PARAM
register(RebuildCommand)

class LoadJobCommand(BuildCommand):
    '''Loads a job from a file that was created with --to-file'''

    commands = ['load']
    commandGroup = CG_BUILD
    paramHelp = '<path>'

    def addParameters(self, argDef):
        self.addBuildParameters(argDef)
        rMakeCommand.addParameters(self, argDef)

    def runCommand(self, client, cfg, argSet, args):
        if self.verbose:
            log.setVerbosity(log.DEBUG)
        else:
            log.setVerbosity(log.INFO)
        command, loadPath = self.requireParameters(args, 'path')
        self._prep(client, argSet)
        job = client.loadJobFromFile(loadPath)
        return self._build(client, job, argSet)
register(LoadJobCommand)

class RestartCommand(BuildCommand):
    '''Restarts the specified job'''

    commands = ['restart']
    commandGroup = CG_BUILD
    paramHelp = '<jobId> [<troveSpec>]*'
    help = 'Restart an earlier job'

    def addParameters(self, argDef):
        self.addBuildParameters(argDef)
        rMakeCommand.addParameters(self, argDef)
        argDef['exclude'] = MULT_PARAM
        argDef['update'] = MULT_PARAM
        argDef['update-config'] = MULT_PARAM
        argDef['no-update'] = NO_PARAM
        argDef['clear-build-list'] = NO_PARAM
        argDef['clear-prebuilt-list'] = NO_PARAM
        argDef['ignore-rebuild-deps'] = NO_PARAM
        argDef['ignore-external-rebuild-deps'] = NO_PARAM

    def runCommand(self, client, cfg, argSet, args):
        if self.verbose:
            log.setVerbosity(log.DEBUG)
        else:
            log.setVerbosity(log.INFO)
        command, jobId, troveSpecs = self.requireParameters(args, 'jobId',
                                                            allowExtra=True)
        jobId = _getJobIdOrUUId(jobId)

        noUpdate = argSet.pop('no-update', False)
        clearBuildList = argSet.pop('clear-build-list', False)
        clearPrebuiltList = argSet.pop('clear-prebuilt-list', False)
        updateConfigKeys = argSet.pop('update-config', None)
        if noUpdate:
            updateSpecs = ['-*']
        else:
            updateSpecs = []
        updateSpecs.extend(argSet.pop('update', []))
        excludeSpecs = argSet.pop('exclude', [])
        self._prep(client, argSet)

        job = client.createRestartJob(jobId, troveSpecs,
                                  updateSpecs=updateSpecs,
                                  excludeSpecs=excludeSpecs,
                                  updateConfigKeys=updateConfigKeys,
                                  clearBuildList=clearBuildList,
                                  clearPrebuiltList=clearPrebuiltList)
        return self._build(client, job, argSet)
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
            'source-only'             : "Only commit the source changes",
            'exclude'                 : "Do not commit from specified"
                                        " sources",
            'message'                 : "The message to give for all"
                                        " committed sources"}

    def addParameters(self, argDef):
        argDef['source-only'] = NO_PARAM
        argDef['message'] = '-m', ONE_PARAM
        argDef['exclude'] = MULT_PARAM
        argDef['to-file'] = ONE_PARAM
        argDef['commit-outdated-sources'] = NO_PARAM
        rMakeCommand.addParameters(self, argDef)

    def runCommand(self, client, cfg, argSet, args):
        command, jobIds = self.requireParameters(args, ['jobId'],
                                                 appendExtra=True)
        commitOutdated = argSet.pop('commit-outdated-sources', False)
        sourceOnly = argSet.pop('source-only', False)
        message = argSet.pop('message', None)
        excludeSpecs = argSet.pop('exclude', None)
        jobIds = _getJobIdOrUUIds(jobIds)
        toFile = argSet.pop('to-file', None)
        success = client.commitJobs(jobIds,
                                    commitOutdatedSources=commitOutdated,
                                    commitWithFailures=True, waitForJob=True,
                                    sourceOnly=sourceOnly,
                                    message=message,
                                    excludeSpecs=excludeSpecs,
                                    writeToFile=toFile)
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
            'tracebacks'      : 'Show tracebacks',
            'all'             : 'Show all jobs (not just last 20)',
            'active'          : 'Show only active jobs',
            'show-config'     : 'Show configuration for this job',
           }


    def addParameters(self, argDef):
        argDef['troves'] = NO_PARAM
        argDef['info'] = NO_PARAM
        argDef['tracebacks'] = NO_PARAM
        argDef['full-versions'] = NO_PARAM
        argDef['labels']     = NO_PARAM
        argDef['flavors']    = NO_PARAM
        argDef['logs']       = NO_PARAM
        argDef['watch']      = NO_PARAM
        argDef['all']        = NO_PARAM
        argDef['active']        = NO_PARAM
        argDef['show-config'] = NO_PARAM
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
        showConfig     = argSet.pop('show-config', False)
        if argSet.pop('all', False):
            limit = None
        else:
            limit = 20
        activeOnly     = argSet.pop('active', False)
        watchJob       = argSet.pop('watch', False)
        query.displayJobInfo(client, jobId, troveSpecs,
                                    displayTroves=displayTroves,
                                    displayDetails=displayDetails,
                                    showLogs=showLogs,
                                    showBuildLogs=showLogs,
                                    showFullVersions=showFullVersions,
                                    showFullFlavors=showFullFlavors,
                                    showLabels=showLabels,
                                    showTracebacks=showTracebacks,
                                    showConfig=showConfig,
                                    jobLimit=limit,
                                    activeOnly=activeOnly)
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
    paramHelp = "<jobId> <trove>"

    commands = ['chroot']

    docs = {'super' :
             'Run as a user capable of modifying the contents of the root',
             'path' : 'Specify the chroot path to use'}

    def addParameters(self, argDef):
        argDef['super'] = NO_PARAM
        argDef['path'] = ONE_PARAM
        rMakeCommand.addParameters(self, argDef)

    def _getChroot(self, chroot):
        return '_local_', chroot

    def runCommand(self, client, cfg, argSet, args):
        command, jobId, troveSpec = self.requireParameters(args,
                                                        ['jobId'],
                                                        allowExtra=True,
                                                        maxExtra=1)
        superUser = argSet.pop('super', False)
        path = argSet.pop('path', None)
        if path:
            chrootHost, chrootPath = self._getChroot(path)
        else:
            chrootHost = chrootPath = None
        if not troveSpec:
            troveSpec = None
        else:
            troveSpec = troveSpec[0]
        client.startChrootSession(jobId, troveSpec, ['/bin/bash', '-l'],
                                  superUser=superUser,
                                  chrootHost=chrootHost,
                                  chrootPath=chrootPath)
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

from conary import cvc
class CheckoutCommand(cvc.CheckoutCommand,rMakeCommand):
    # Move this to the same section as NewPkg
    commandGroup = 'Setup Commands'
    def processConfigOptions(self, *args, **kw):
        return rMakeCommand.processConfigOptions(self, *args, **kw)

    def runCommand(self, client, cfg, argSet, args):
        return cvc.CheckoutCommand.runCommand(self, cfg, argSet, args,
                                              repos=client.getRepos())
register(CheckoutCommand)

class NewPkgCommand(cvc.NewPkgCommand, rMakeCommand):
    commandGroup = 'Setup Commands'
    def processConfigOptions(self, *args, **kw):
        return rMakeCommand.processConfigOptions(self, *args, **kw)

    def runCommand(self, client, cfg, argSet, args):
        return cvc.NewPkgCommand.runCommand(self, cfg, argSet, args,
                                            repos=client.getRepos())
register(NewPkgCommand)

class ContextCommand(cvc.ContextCommand, rMakeCommand):
    def processConfigOptions(self, *args, **kw):
        return rMakeCommand.processConfigOptions(self, *args, **kw)

    def runCommand(self, client, cfg, argSet, args):
        return cvc.ContextCommand.runCommand(self, cfg, argSet, args,
                                             repos=client.getRepos())
register(ContextCommand)

class BuildImageCommand(BuildCommand):
    commands = ['buildimage']
    commandGroup = CG_BUILD

    def addParameters(self, argDef):
        argDef['option'] = MULT_PARAM
        BuildCommand.addParameters(self, argDef)

    def runCommand(self, client, cfg, argSet, args):
        (command, project,
         troveSpec, imageType) = self.requireParameters(args, ['project',
                                                               'troveSpec',
                                                               'imageType'])
        options = {}
        for option in argSet.pop('option', []):
            key, value = option.split('=', 1)
            options[key] = value
        job = client.createImageJob(project, troveSpec, imageType, options)
        return self._build(client, job, argSet)

register(BuildImageCommand)


def addCommands(main):
    for command in _commands:
        main._registerCommand(command)


