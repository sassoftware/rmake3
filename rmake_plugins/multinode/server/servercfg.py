#
# Copyright (c) 2007, 2009 rPath, Inc.
#
# All rights reserved.
#

import urllib2

from conary.lib import cfgtypes

from rmake.server import servercfg
from rmake import errors
from rmake.lib import procutil


def getMessageBusHost(self, qualified=False):
    host = self.messageBusHost
    if host in (None, 'LOCAL'):
        if qualified:
            return procutil.getNetName()
        else:
            return 'localhost'
    else:
        return host


ServerConfig = dict(
    reposUrl       = (cfgtypes.CfgString, 'https://LOCAL:7777'),
    rmakeUrl       = (cfgtypes.CfgString, 'https://localhost:9999'),
    proxyUrl       = (cfgtypes.CfgString, None),
    rbuilderUrl    = (cfgtypes.CfgString, 'https://localhost/'),
    # if None, start one locally
    # if "LOCAL", don't start one but still use localhost
    messageBusHost = (cfgtypes.CfgString, None),
    messageBusPort = (cfgtypes.CfgInt, 50900),

    getMessageBusHost=getMessageBusHost,
    )

def getAuthUrl(self):
    return self.rbuilderUrl

def checkBuildSanity(self):
    #cancel out build sanity check - this is not a build node.
    return True

def sanityCheckForStart(self):
    if self.proxyUrl is None:
        self.proxyUrl = self.rbuilderUrl
    if self.hostName == 'localhost':
        self.hostName = procutil.getNetName()
    self.oldSanityCheck()
    try:
        try:
            urllib2.urlopen(self.rbuilderUrl).read(1024)
        except urllib2.HTTPError, err:
            if 200 <= err.code < 400:
                # Something benign like a redirect
                pass
            else:
                raise
    except Exception, err:
        raise errors.RmakeError('Could not access rbuilder at %s.  '
                'Please ensure you have a line "rbuilderUrl '
                'https://<yourRbuilder>" set correctly in your serverrc '
                'file.  Error: %s' % (self.rbuilderUrl, err))


def updateConfig():
    mainConfig = servercfg.rMakeConfiguration
    for key, value in ServerConfig.items():
        setattr(mainConfig, key, value)
    if not hasattr(mainConfig, 'oldSanityCheck'):
        mainConfig.oldSanityCheck = mainConfig.sanityCheckForStart
        mainConfig.oldGetAuthUrl = mainConfig.getAuthUrl
        mainConfig.oldCheckBuildSanity = mainConfig.checkBuildSanity

    mainConfig.checkBuildSanity = checkBuildSanity
    mainConfig.getAuthUrl = getAuthUrl
    mainConfig.sanityCheckForStart = sanityCheckForStart

def resetConfig():
    mainConfig = servercfg.rMakeConfiguration
    if not hasattr(mainConfig, 'oldSanityCheck'):
        return
    mainConfig.checkBuildSanity = mainConfig.oldCheckBuildSanity
    mainConfig.getAuthUrl = mainConfig.oldGetAuthUrl
    mainConfig.sanityCheckForStart = mainConfig.oldSanityCheck
