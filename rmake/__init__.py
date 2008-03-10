#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
rMake, build utility for conary
"""
def initializePlugins(pluginDirs, disabledPlugins=None):
    global pluginManager
    from rmake import plugins
    pluginManager = plugins.PluginManager(pluginDirs=pluginDirs,
                                          disabledPlugins=disabledPlugins)
    pluginManager.loadPlugins()
    pluginManager.callLibraryHook('library_preInit')
