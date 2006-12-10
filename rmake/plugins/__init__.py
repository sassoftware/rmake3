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
rMake, build utility for conary - plugin support
"""
from rmake import subscribers
from rmake.lib import pluginlib
from rmake.plugins.plugin import *

class PluginManager(pluginlib.PluginManager):
    def __init__(self, pluginDirs=None, disabledPlugins=None):
        pluginlib.PluginManager.__init__(self, pluginDirs, disabledPlugins,
                                         pluginPrefix='rmake_plugins',
                                         supportedTypes=[TYPE_CLIENT,
                                                         TYPE_SERVER,
                                                         TYPE_SUBSCRIBER])
        self.loadPlugins()
        # make subscriber plugins available.
        subscribers.loadPlugins(self.getPluginsByType(TYPE_SUBSCRIBER))

    def callClientHook(self, hookName, *args, **kw):
        self.callHook(TYPE_CLIENT, hookName, *args, **kw)

    def callServerHook(self, hookName, *args, **kw):
        self.callHook(TYPE_SERVER, hookName, *args, **kw)

    def callSubscriberHook(self, hookName, *args, **kw):
        self.callHook(TYPE_SUBSCRIBER, hookName, *args, **kw)

def getPluginManager(argv, configClass):
    """
        Handles plugin parameter parsing.  Unfortunately, plugin
        parameter parsing must happen very early on in the command-line parsing
        -- loading or not loading a plugin may change what parameters are 
        valid, for example.  For that reason, we have to do some hand
        parsing.

        Limitations: in order to reduce the complexity of this hand-parsing,
        plugin parameters are not allowed in contexts, and they cannot
        be specified as --config options.

        Suggestions on removing these limitations are welcome.
    """
    if '--no-plugins' in argv:
        argv.remove('--no-plugins')
        return PluginManager([])

    if '--skip-default-config' in argv:
        read = False
    else:
        read = True
    # create an instance of our configuration file.  Ingore errors
    # that might arise due to unknown options or changed option types,
    # e.g. - we are only interested in the plugin dirs and usePlugins
    # options.
    cfg = configClass(readConfigFiles=read, ignoreErrors=True)
    if not cfg.usePlugins:
        return PluginManager([])

    pluginDirInfo = [ x for x in argv if x.startswith('--plugin-dirs=')]

    if pluginDirInfo:
        pluginDirs = pluginDirInfo[-1].split('=', 1)[1].split(',')
        [ argv.remove(x) for x in pluginDirInfo ]
    else:
        pluginDirs = cfg.pluginDirs

    disabledPlugins = [ x[0] for x in cfg.usePlugin.items() if not x[1] ]
    return PluginManager(pluginDirs, disabledPlugins)
