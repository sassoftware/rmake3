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


"""
rMake, build utility for conary - plugin support
"""
from rmake import subscribers
from rmake.lib import pluginlib
from rmake.plugins.plugin import *

class PluginManager(pluginlib.PluginManager):
    def __init__(self, pluginDirs=None, disabledPlugins=None):
        pluginlib.PluginManager.__init__(self, pluginDirs, disabledPlugins,
                                         pluginPrefix='rmake_plugins')

    def loadPlugins(self):
        pluginlib.PluginManager.loadPlugins(self)
        # make subscriber plugins available.
        subscribers.loadPlugins(self.getPluginsByType(TYPE_SUBSCRIBER))

    def callClientHook(self, hookName, *args, **kw):
        self.callHook(TYPE_CLIENT, hookName, *args, **kw)

    def callLibraryHook(self, hookName, *args, **kw):
        self.callHook(TYPE_LIBRARY, hookName, *args, **kw)

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
    readNext = False
    for item in argv:
        if readNext:
            cfg.read(item)
            readNext = False
            continue
        if item.startswith('--config-file='):
            file = item.split('=', 0)[1]
            cfg.read(file)
        elif item == '--config-file':
            readNext = True
    if not getattr(cfg, 'usePlugins', True):
        return PluginManager([])

    pluginDirInfo = [ x for x in argv if x.startswith('--plugin-dirs=')]

    if pluginDirInfo:
        pluginDirs = pluginDirInfo[-1].split('=', 1)[1].split(',')
        [ argv.remove(x) for x in pluginDirInfo ]
    else:
        pluginDirs = cfg.pluginDirs

    disabledPlugins = [ x[0] for x in cfg.usePlugin.items() if not x[1] ]
    p = PluginManager(pluginDirs, disabledPlugins)
    p.loadPlugins()
    return p
