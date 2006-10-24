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
Describes a BuildConfiguration, which is close to, but neither a subset nor
a superset of a conarycfg file.
"""
import os
import re

from conary import conarycfg
from conary import versions
from conary.lib import cfg
from conary.lib import log
from conary.lib import sha1helper
from conary.conarycfg import CfgLabel
from conary.conarycfg import ParseError
from conary.conaryclient import cmdline
from conary.lib.cfgtypes import (CfgBool, CfgPath, CfgList, CfgDict, CfgString,
                                 CfgInt, CfgType, CfgQuotedLineList)

from rmake.lib import apiutils, daemon
from rmake import compat, plugins

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
        s = plugins.SubscriberFactory(name, protocol, uri)
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

class RmakeBuildContext(cfg.ConfigSection):

    defaultBuildReqs     = (CfgList(CfgString),
                            ['bash:runtime',
                             'coreutils:runtime', 'filesystem',
                             'conary:runtime',
                             'conary-build:runtime', 'epdb', 'dev:runtime', 
                             'grep:runtime', 'procps:runtime', 'sed:runtime',
                             'findutils:runtime', 'gawk:runtime'
                             ])
    enforceManagedPolicy = (CfgBool, False)
    resolveTroves        = (CfgList(CfgQuotedLineList(CfgTroveSpec)),
                            [[('group-dist', None, None)]])
    resolveTrovesOnly    = (CfgBool, False)
    strictMode           = (CfgBool, False)
    subscribe            = (CfgSubscriberDict(CfgSubscriber), {})
    targetLabel          = (CfgLabel, versions.Label('NONE@LOCAL:NONE'))
    uuid                 = (CfgUUID, '')


    def __init__(self, parent, doc=None):
        cfg.ConfigSection.__init__(self, parent, doc=None)

        for info in conarycfg.ConaryContext._getConfigOptions():
            if info[0] not in self:
                self.addConfigOption(*info)

class BuildConfiguration(conarycfg.ConaryConfiguration):

    buildTroveSpecs      = CfgList(CfgTroveSpec)
    resolveTroveTups     = CfgList(CfgQuotedLineList(CfgTroveTuple))

    # Here are options that are not visible from the command-line
    # and should not be displayed.  They are job-specific.  However,
    # they must be stored with the job, parsed with the job, etc.

    _hiddenOptions = [ 'buildTroveSpecs', 'resolveTroveTups' ]

    _strictOptions = [ 'buildFlavor', 'buildLabel',
                       'flavor', 'installLabelPath', 'repositoryMap', 'root',
                       'user', 'name', 'contact' ]
    _defaultSectionType   =  RmakeBuildContext

    def __init__(self, readConfigFiles=False, root='', conaryConfig=None, 
                 serverConfig=None):
        # we default the value of these items to whatever they
        # are set to on the local system's conaryrc.

        conarycfg.ConaryConfiguration.__init__(self, readConfigFiles=False)
        for info in RmakeBuildContext._getConfigOptions():
            if info[0] not in self:
                self.addConfigOption(*info)

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

        # these values are not set based on 
        # config file values - we don't want to touch the system database, 
        # and we don't want to use conary's logging mechanism.
        self.root = ':memory:'
        self.dbPath = ':memory:'
        self.logFile = []
        for option in self._hiddenOptions:
            del self._lowerCaseMap[option.lower()]

        self.useConaryConfig(conaryConfig)
        self.setServerConfig(serverConfig)

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

        if not conaryConfig:
            return

        # copy in conary config values that we haven't
        # overrided from the rmake config
        for key in self.iterkeys():
            if self.strictMode and key not in self._strictOptions:
                continue
            if  _shouldOverwrite(key, self, conaryConfig):
                self[key] = conaryConfig[key]

        if self.strictMode:
            self.enforceManagedPolicy = True

    def setServerConfig(self, serverCfg):
        self.serverCfg = serverCfg
        if serverCfg:
            # we need to be careful of duplicate entries here,
            # so we have to feed the user entry data in the
            # right order.
            for entry in reversed(serverCfg.user):
                self.user.append(entry)
        if serverCfg:
            self.repositoryMap.update(serverCfg.getRepositoryMap())


    def getTargetLabel(self, versionOrLabel):
        if isinstance(versionOrLabel, versions.Label):
            cookLabel = versionOrLabel
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
                host = self.serverCfg.serverName
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
            if val == cfgItem.default:
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
                if not lines:
                    obj[name] = lines

                for line in d.get(name, []):
                    setattr(obj, name,
                            obj._options[name].parseString(obj[name], line))
        return obj


apiutils.register(apiutils.api_freezable(BuildConfiguration),
                  'BuildConfiguration')
