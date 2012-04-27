#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


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
