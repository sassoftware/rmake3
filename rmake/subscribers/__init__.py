import sys

from rmake import errors

_builtInsLoaded = False
_registeredProtocols = {}
def registerProtocol(protocol, class_):
    _registeredProtocols[protocol] = class_


def _loadBuiltIns():
    global _builtInsLoaded
    pluginNames = ['mailto', 'xmlrpc', 'irc']
    for pluginName in pluginNames:
        module = __import__('rmake.subscribers.' + pluginName, {}, {}, 
                            ['rmake.subscribers'])
        for class_ in module.__dict__.values():
            if hasattr(class_, 'protocol'):
                registerProtocol(class_.protocol, class_)
        sys.modules[__name__].__dict__[pluginName] = module
    _builtinsLoaded = True

def loadPlugins(pluginList):
    if not _builtInsLoaded:
        _loadBuiltIns()
    for plugin in pluginList:
        registerProtocol(plugin.protocol, plugin.subscriber_get())


def SubscriberFactory(name, protocol, uri):
    if not _builtInsLoaded:
        _loadBuiltIns()
    try:
        return _registeredProtocols[protocol](name, uri)
    except KeyError:
        raise errors.RmakeError('cannot get subscriber for %s: Unknown protocol' % uri)

