#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Describes a BuildConfiguration, which is close to, but neither a subset nor
a superset of a conarycfg file.
"""
import os
import re

from conary import conarycfg
from conary import versions
from conary.lib import cfg,cfgtypes
from conary.lib import log
from conary.lib import sha1helper
from conary.conarycfg import CfgLabel
from conary.conarycfg import ParseError
from conary.conaryclient import cmdline
from conary.lib.cfgtypes import (CfgBool, CfgPath, CfgList, CfgDict, CfgString,
                                 CfgInt, CfgType, CfgQuotedLineList, 
                                 CfgPathList)

from rmake.lib import apiutils, daemon, logger
from rmake import compat, errors, subscribers

class CfgTroveSpec(CfgType):
    def parseString(self, val):
        return cmdline.parseTroveSpec(val)

    def format(self, val, displayOptions=None):
        if not val[2] is None:
            flavorStr = '[%s]' % val[2]
        else:
            flavorStr = ''
        if val[1]:
            verStr = '=%s' % val[1]
        else:
            verStr = ''

        return '%s%s%s' % (val[0], verStr, flavorStr)

class CfgTroveTuple(CfgType):
    def parseString(self, val):
        (name, version, flavor) = cmdline.parseTroveSpec(val)
        return (name, versions.VersionFromString(version), flavor)

    def format(self, val, displayOptions=None):
        return '%s=%s[%s]' % val

class CfgSubscriberDict(CfgDict):
    def parseValueString(self, key, value):
        return self.valueType.parseString(key, value)

class CfgSubscriber(CfgType):

    def parseString(self, name, val):
        protocol, uri = val.split(None, 1)
        try:
            s = subscribers.SubscriberFactory(name, protocol, uri)
        except errors.RmakeError, err:
            raise ParseError(err)
        return s

    def updateFromString(self, s, str):
        s.parse(*str.split(None, 1))
        return s

    def toStrings(self, s, displayOptions):
        return s.freezeData()

class CfgUUID(CfgType):

    def parseString(self, val):
        if not val:
            return ''
        newVal = val.replace('-', '').lower()
        if not re.match('^[0-9a-f]{32}$', newVal):
            raise ParseError, "Invalid UUID: '%s'" % val
        return newVal

    def toStrings(self, val, displayOptions):
        return [ val ]

class CfgUser(CfgType):
    def parseString(self, str):
        val = str.split()
        if len(val) < 1 or len(val) > 2:
            raise ParseError("expected <user> [<password>]")
        elif len(val) == 1:
            return (val[0], None)
        else:
            return tuple(val)

    def format(self, val, displayOptions=None):
        user, password = val
        if password is None:
            return user
        elif displayOptions.get('hidePasswords'):
            return '%s <password>' % (user)
        else:
            return '%s %s' % (user, password)


class RmakeBuildContext(cfg.ConfigSection):

    copyInConary         = (CfgBool, False)
    copyInConfig         = (CfgBool, True)
    defaultBuildReqs     = (CfgList(CfgString),
                            ['bash:runtime',
                             'coreutils:runtime', 'filesystem',
                             'conary:runtime',
                             'conary-build:runtime', 'dev:runtime',
                             'grep:runtime', 'sed:runtime',
                             'findutils:runtime', 'gawk:runtime'])
    resolveTroves        = (CfgList(CfgQuotedLineList(CfgTroveSpec)),
                            [[('group-dist', None, None)]])
    matchTroveRule       = (CfgList(CfgString), [])
    resolveTrovesOnly    = (CfgBool, False)
    reuseRoots           = (CfgBool, False)
    strictMode           = (CfgBool, False)
    subscribe            = (CfgSubscriberDict(CfgSubscriber), {})
    targetLabel          = (CfgLabel, versions.Label('NONE@local:NONE'))
    uuid                 = (CfgUUID, '')

    def __init__(self, parent, doc=None):
        cfg.ConfigSection.__init__(self, parent, doc=None)

        for info in conarycfg.ConaryContext._getConfigOptions():
            if info[0] not in self:
                self.addConfigOption(*info)

class BuildConfiguration(conarycfg.ConaryConfiguration):

    buildTroveSpecs      = CfgList(CfgTroveSpec)
    resolveTroveTups     = CfgList(CfgQuotedLineList(CfgTroveTuple))
    recurseGroups        = (CfgInt, 0)
    prepOnly             = (CfgBool, False)
    pluginDirs           = (CfgPathList, ['/usr/share/rmake/plugins',
                                          '~/.rmake/plugins.d'])
    usePlugin            = CfgDict(CfgBool)
    usePlugins           = (CfgBool, True)
    jobContext           = CfgList(CfgInt)

    # Here are options that are not visible from the command-line
    # and should not be displayed.  They are job-specific.  However,
    # they must be stored with the job, parsed with the job, etc.

    _hiddenOptions = [ 'buildTroveSpecs', 'resolveTroveTups', 'jobContext',
                       'recurseGroups' ]

    _strictOptions = [ 'buildFlavor', 'buildLabel', 'cleanAfterCook','flavor',
                       'installLabelPath', 'repositoryMap', 'root',
                       'user', 'name', 'contact', 'signatureKey', 'dbPath',
                       'proxy', 'conaryProxy', 'lookaside', 'entitlement' ]

    _dirsToCopy = ['archDirs', 'mirrorDirs', 'siteConfigPath', 'useDirs', 
                   'componentDirs']
    _pathsToCopy = ['defaultMacros']
    _defaultSectionType   =  RmakeBuildContext

    def __init__(self, readConfigFiles=False, root='', conaryConfig=None, 
                 serverConfig=None, ignoreErrors=False, log=None, 
                 strictMode=None):
        # we default the value of these items to whatever they
        # are set to on the local system's conaryrc.
        if log is None:
            log = logger.Logger('buildcfg')

        conarycfg.ConaryConfiguration.__init__(self, readConfigFiles=False)
        if hasattr(self, 'setIgnoreErrors'):
            self.setIgnoreErrors(ignoreErrors)
        for info in RmakeBuildContext._getConfigOptions():
            if info[0] not in self:
                self.addConfigOption(*info)
        if strictMode is not None:
            self.strictMode = strictMode
        if not hasattr(self, 'rmakeUrl'):
            self.rmakeUrl = None

        if readConfigFiles:
            if os.path.exists(root + '/etc/rmake/clientrc'):
                log.warning(root + '/etc/rmake/clientrc should be renamed'
                                   ' to /etc/rmake/rmakerc')
                self.read(root + '/etc/rmake/clientrc', exception=False)
            self.read(root + '/etc/rmake/rmakerc', exception=False)
            if os.environ.has_key("HOME"):
                self.read(root + os.environ["HOME"] + "/" + ".rmakerc",
                          exception=False)
            self.read('rmakerc', exception=False)

        if self.strictMode:
            self.enforceManagedPolicy = True
            self.copyInConary = False
            self.copyInConfig = False

        # these values are not set based on 
        # config file values - we don't want to touch the system database, 
        # and we don't want to use conary's logging mechanism.
        self.root = ':memory:'
        self.dbPath = ':memory:'
        self.logFile = []
        for option in self._hiddenOptions:
            del self._lowerCaseMap[option.lower()]

        self.useConaryConfig(conaryConfig)
        if serverConfig:
            self.reposName = serverConfig.reposName
            self.repositoryMap.update(serverConfig.getRepositoryMap())
            self.user.extend(serverConfig.reposUser)

    def useConaryConfig(self, conaryConfig):
        def _shouldOverwrite(key, current, new):
            if key not in new:
                return False
            if compat.ConaryVersion().supportsConfigIsDefault():
                if (current.isDefault(key) and
                    current[key] == current.getDefaultValue(key) and
                   (not new.isDefault(key) or
                    new[key] != new.getDefaultValue(key))):
                    return True
            elif (current[key] is current.getDefaultValue(key) or
                  current[key] == current.getDefaultValue(key)
                  and (not new[key] is new.getDefaultValue(key)
                       and not new[key] == new.getDefaultValue(key))):
                return True
            return False
        if self.strictMode:
            if not conaryConfig:
                conaryConfig = conarycfg.ConaryConfiguration(False)
            for key in self.iterkeys():
                if key not in self._strictOptions and key in conaryConfig:
                    self.resetToDefault(key)

        if not conaryConfig:
            return

        # copy in conary config values that we haven't
        # overrided from the rmake config
        for key in self.iterkeys():
            if self.strictMode and key not in self._strictOptions:
                continue
            if  _shouldOverwrite(key, self, conaryConfig):
                self[key] = conaryConfig[key]

        for sectionName in conaryConfig.iterSectionNames():
            conarySection = conaryConfig.getSection(sectionName)
            if not self.hasSection(sectionName):
                self._addSection(sectionName, self._defaultSectionType(self))
            mySection = self.getSection(sectionName)
            for key in mySection.iterkeys():
                if self.strictMode and key not in self._strictOptions:
                    continue
                if  _shouldOverwrite(key, mySection, conarySection):
                    mySection[key] = conarySection[key]

        if self.strictMode:
            self.enforceManagedPolicy = True
            self.copyInConary = False
            self.copyInConfig = False
        if not self.copyInConfig:
            for option in self._dirsToCopy + self._pathsToCopy:
                self.resetToDefault(option)

    def getServerUri(self):
        if self.rmakeUrl:
            return self.rmakeUrl
        return 'unix:///var/lib/rmake/socket'

    def limitToHosts(self, hosts):
        if isinstance(hosts, str):
            hosts = [hosts]
        for host in hosts:
            if '@' in host or '=' in host:
                raise ParseError('Invalid host "%s"' % host)
            self.addMatchRule('=%s@' % host)

    def limitToLabels(self, labels):
        if isinstance(labels, str):
            labels = [labels]
        for label in labels:
            label = versions.Label(label)
            self.addMatchRule('=%s' % label)

    def addMatchRule(self, matchRule):
        self.configLine('matchTroveRule %s' % matchRule)

    def clearMatchRules(self):
        self.matchTroveRule = []
        for section in self.iterSections():
            section.matchTroveRule = []

    def getTargetLabel(self, versionOrLabel):
        if isinstance(versionOrLabel, versions.Label):
            cookLabel = versionOrLabel
        elif isinstance(versionOrLabel, versions.Branch):
            cookLabel = versionOrLabel.label()
        else:
            cookLabel = versionOrLabel.trailingLabel()

        targetLabel = self.targetLabel
        if targetLabel:
            # we treat NONE in the label as being a special target,
            # if your targetLabel is localhost@rpl:NONE, we build 
            # onto localhost@rpl:<branch> where branch is the branch
            # of the source version.

            needNewLabel = False
            if targetLabel.getHost().lower() == 'none':
                needNewLabel = True
                host = self.reposName
            else:
                host = targetLabel.getHost()

            if targetLabel.getNamespace().lower() == 'none':
                needNewLabel = True
                nameSpace = cookLabel.getNamespace()
            else:
                nameSpace = targetLabel.getNamespace()

            if targetLabel.branch.lower() == 'none':
                needNewLabel = True
                branch = cookLabel.branch
            else:
                branch = targetLabel.branch

            if needNewLabel:
                targetLabel = '%s@%s:%s' % (host, nameSpace, branch)
                targetLabel = versions.Label(targetLabel)
            return targetLabel
        else:
            return version.getTrailingLabel()

    def dropContexts(self):
        self._sections = {}

    def storeConaryCfg(self, out):
        conaryCfg = conarycfg.ConaryConfiguration(False)
        for key, value in self.iteritems():
            if self.isDefault(key):
                continue
            if key in conaryCfg:
                if key == 'context':
                    # we're not writing out contexts!
                    continue
                conaryCfg[key] = value
        conaryCfg.store(out, includeDocs=False)

    def _writeKey(self, out, cfgItem, value, options):
        if cfgItem.name in self._hiddenOptions:
            if not options.get('displayHidden', False):
                return
        conarycfg.ConaryConfiguration._writeKey(self, out, cfgItem,
                                                self[cfgItem.name], options)

    def __freeze__(self):
        """ 
            Support the freeze mechanism to allow a build config to be 
            sent via xmlrpc.  Basically converts to a set of strings
            that can be read in on the other side.
        """
        configOptions = dict(prettyPrint=False, expandPaths=True)
        d = {}
        for name, cfgItem in self._options.iteritems():
            val = self[name]
            # _Path objects may change even when there at the default.
            if (val == cfgItem.default and not isinstance(val, cfgtypes._Path)
                and not (isinstance(val, list)
                         and val and isinstance(val[0], cfgtypes._Path))):
                continue
            if val is None:
                continue
            else:
                d[name] = list(cfgItem.valueType.toStrings(val, configOptions))
        return d

    @classmethod
    def __thaw__(class_, d):
        """ 
            Support the thaw mechanism to allow a build config to be 
            read from xmlrpc.  Converts back from a set of strings.
        """

        obj = class_(False)
        for name, cfgItem in obj._options.iteritems():
            if name in d:
                lines = d[name]
                if not lines and obj[name] is None:
                    obj[name] = lines

                for line in d.get(name, []):
                    value = obj._options[name].parseString(obj[name], line)
                    if name in obj: # it could be a hidden attribute,
                                    # in which case we can't use setitem.
                                    # but if we can we want to trigger the 
                                    # default handling...
                        obj[name] = value
                    else:
                        setattr(obj, name, value)
        return obj


apiutils.register(apiutils.api_freezable(BuildConfiguration),
                  'BuildConfiguration')

class SanitizedBuildConfiguration:

    @staticmethod
    def __freeze__(cfg):
        cfg = apiutils.freeze('BuildConfiguration', cfg)
        cfg['user'] = []
        cfg['entitlement'] = []
        return cfg

    @staticmethod
    def __thaw__(cfg):
        return apiutils.thaw('BuildConfiguration', cfg)
apiutils.register(SanitizedBuildConfiguration)
