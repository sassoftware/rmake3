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
rMake, build utility for conary - plugins
"""
import sys
import urllib

from rmake import errors

# Note: this is not supposed to be a fully featured plugin interface atm,
# simply a sort of 'hook' for one to be implemented later.

_pluginsLoaded = False
_registeredProtocols = {}
def registerProtocol(protocol, class_):
    _registeredProtocols[protocol] = class_


def _loadPlugins():
    pluginNames = ['mailto', 'xmlrpc', 'irc']
    for pluginName in pluginNames:
        module = __import__('rmake.plugins.' + pluginName, {}, {}, 
                            ['rmake.plugins'])
        for class_ in module.__dict__.values():
            if hasattr(class_, 'protocol'):
                registerProtocol(class_.protocol, class_)
        sys.modules[__name__].__dict__[pluginName] = module
    _pluginsLoaded = True


def SubscriberFactory(name, protocol, uri):
    if not _pluginsLoaded:
        _loadPlugins()
    try:
        return _registeredProtocols[protocol](name, uri)
    except KeyError:
        raise errors.RmakeError('cannot get subscriber for %s: Unknown protocol' % uri)

