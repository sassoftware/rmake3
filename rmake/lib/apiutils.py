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
Along with apirpc, implements an API-validating and versioning scheme for
xmlrpc calls.
"""

import inspect
import itertools
import traceback

from conary import versions
from conary.deps import deps
from conary.deps.deps import ThawFlavor
from conary.deps.deps import ThawDependencySet
from conary.lib import util

# fix for conary wrapping some strings as protected strings.
# make sure that there's a dispatcher in place that will just convert them
# to normal strings.
if hasattr(util, 'ProtectedString'):
    import xmlrpclib
    xmlrpclib.Marshaller.dispatch[util.ProtectedString] = xmlrpclib.Marshaller.dump_string

from rmake.lib import procutil

# ------------------ registry for api param types ------------
apitypes = { None : None }

def register(class_, name=None):
    if not name:
        if hasattr(class_, 'name'):
            name = class_.name
        else:
            name = class_.__name__
    apitypes[name] = class_

def registerMethods(name, freeze, thaw):
    apitypes[name] = (freeze, thaw)

def registerThaw(name, thawMethod):
    if name in apitypes:
        apitypes[name] = (apitypes[name][0], thawMethod)
    else:
        apitypes[name] = (None, thawMethod)

def registerFreeze(name, freezeMethod):
    if name in apitypes:
        apitypes[name] = (freezeMethod, apitypes[name][1])
    else:
        apitypes[name] = (freezeMethod, None)

def isRegistered(name):
    return name in apitypes

def canHandle(name, instance):
    if name not in apitypes:
        return False
    handler = apitypes[name]
    if not inspect.isclass(handler):
        return True
    return isinstance(instance, handler)

# ----- decorators for describing a method's API.

def api(version=0, allowed=None):
    """
        Decorator that describes the current version of the
        api as well as supported older versions.
        Allowed should be a list of allowed versions or None.

        For example:
        @api(version=5, allowed=range(2,5))
    """
    def deco(func):
        func.version = version
        if not hasattr(func, 'params'):
            func.params = {version: []}
        if not hasattr(func, 'returnType'):
            func.returnType = {version: None}

        if not allowed:
            func.allowed_versions = set([version])
        else:
            if isinstance(allowed, int):
                func.allowed_versions = set([allowed, version])
            else:
                func.allowed_versions = set(allowed + [version])
        return func
    return deco

def api_parameters(version, *paramList):
    """
        Decorator that describes the parameters accepted and their types
        for a particular version of the api.  Parameters should be classes
        with freeze and thaw methods, or None.  A None implies freezing
        and thawing of this parameter will be done manually or is not needed.

        For example:
        @api(5, api_manual, api_int)
    """
    if not isinstance(version, int):
        raise RuntimeError, 'must specify version for api parameters'

    def deco(func):
        if not hasattr(func, 'params'):
            func.params = {}
        func.params[version] = [ apitypes[x] for x in paramList ]
        return func
    return deco

def api_return(version, returnType):
    """ Decorator to be used to describe the return type of the function for
        a particular version of this method.

        Example usage:
        @api_return(1, api_troveTupleList)
    """
    if not isinstance(version, int):
        raise RuntimeError, 'must specify version for api parameters'

    def deco(func):
        if not hasattr(func, 'returnType'):
            func.returnType = {}
        if isinstance(returnType, str):
            r = apitypes[returnType]
        else:
            r = returnType

        func.returnType[version] = r
        return func
    return deco

def api_nonforking(func):
    func.forking = False
    return func

def api_forking(func):
    func.forking = True
    return func

# --- generic methods to freeze/thaw based on type

def freeze(apitype, item):
    found = False
    if isinstance(apitype, type):
        if not hasattr(apitype, '__freeze__'):
            apitype = apitype.__name__

    if not isinstance(apitype, type):
        apitype = apitypes[apitype]

    if apitype is None:
        return item
    if isinstance(apitype, tuple):
        return apitype[0](item)
    return apitype.__freeze__(item)

def thaw(apitype, item):
    if isinstance(apitype, type):
        if not hasattr(apitype, '__freeze__'):
            apitype = apitype.__name__

    if not isinstance(apitype, type):
        apitype = apitypes[apitype]
    if apitype is None:
        return item
    if isinstance(apitype, tuple):
        return apitype[1](item)
    return apitype.__thaw__(item)

# ---- individual api parameter types below this point. ---

class api_troveTupleList:
    name = 'troveTupleList'

    @staticmethod
    def __freeze__(tupList):
        return [(x[0], x[1].freeze(), (x[2] is not None) and x[2].freeze() or '')
                for x in tupList]

    @staticmethod
    def __thaw__(tupList):
        return [(x[0], versions.ThawVersion(x[1]),
                 ThawFlavor(x[2])) for x in tupList ]
register(api_troveTupleList)

class api_troveContextTupleList:
    name = 'troveContextTupleList'

    @staticmethod
    def __freeze__(tupList):
        results = []
        for x in tupList:
            if len(x) == 3 or not x[3]:
                results.append((x[0], x[1].freeze(), (x[2] is not None) and x[2].freeze() or ''))
            else:
                results.append((x[0], x[1].freeze(), (x[2] is not None) and x[2].freeze() or '', x[3]))
        return results

    @staticmethod
    def __thaw__(tupList):
        results = []
        for tup in tupList:
            if len(tup) == 3 or not tup[3]:
                context = ''
            else:
                context = tup[3]
            results.append((tup[0], versions.ThawVersion(tup[1]), ThawFlavor(tup[2]), context))
        return results
register(api_troveContextTupleList)


class api_installJobList:
    name = 'installJobList'

    @staticmethod
    def __freeze__(jobList):
        return [(x[0], x[2][0].freeze(), x[2][1].freeze(), x[3])
                for x in jobList]

    @staticmethod
    def __thaw__(jobList):
        return [(x[0], (None, None),
                (versions.ThawVersion(x[1]), ThawFlavor(x[2])), x[3]) 
                for x in jobList]
register(api_installJobList)



class api_specList:
    name = 'troveSpecList'

    @staticmethod
    def __freeze__(tupList):
        return [(x[0], x[1] or '', (x[2] is not None) and x[2].freeze() or '')
                for x in tupList]

    @staticmethod
    def __thaw__(tupList):
        return [(x[0], x[1], ThawFlavor(x[2])) for x in tupList ]
register(api_specList)

class api_spec:
    name = 'troveSpec'

    @staticmethod
    def __freeze__(x):
        return (x[0], x[1] or '', (x[2] is not None) and x[2].freeze() or '')

    @staticmethod
    def __thaw__(x):
        return (x[0], x[1], ThawFlavor(x[2]))
register(api_spec)

class api_troveTuple:
    name = 'troveTuple'

    @staticmethod
    def __freeze__((n,v,f)):
        return (n, v.freeze(), (f is not None) and f.freeze() or '')

    @staticmethod
    def __thaw__((n,v,f)):
        return (n, versions.ThawVersion(v), ThawFlavor(f))
register(api_troveTuple)

class api_troveContextTuple:
    name = 'troveContextTuple'

    @staticmethod
    def __freeze__(item):
        if len(item) == 3:
            context = ''
            n,v,f = item
        else:
            n,v,f,context = item

        if not context:
            return (n, v.freeze(), (f is not None) and f.freeze() or '')
        return (n, v.freeze(), (f is not None) and f.freeze() or '', context)

    @staticmethod
    def __thaw__(item):
        if len(item) == 3:
            context = ''
            n,v,f = item
        else:
            n,v,f,context = item
        return (n, versions.ThawVersion(v), ThawFlavor(f), context)
register(api_troveContextTuple)

class api_jobList:
    name = 'jobList'

    @staticmethod
    def __freeze__(jobList):
        return [(x[0], freeze('troveTupleList', x[1])) for x in jobList]

    @staticmethod
    def __thaw__(jobList):
        return [(x[0], thaw('troveTupleList', x[1])) for x in jobList]
register(api_jobList)

class api_version:
    name = 'version'

    @staticmethod
    def __freeze__(version):
        return version.freeze()

    @staticmethod
    def __thaw__(versionStr):
        return versions.ThawVersion(versionStr)
register(api_version)

class api_label:
    name = 'label'

    @staticmethod
    def __freeze__(label):
        return str(label)

    @staticmethod
    def __thaw__(label):
        return versions.Label(label)
register(api_label)


class api_flavor:
    name = 'flavor'

    @staticmethod
    def __freeze__(flavor):
        return flavor.freeze()

    @staticmethod
    def __thaw__(flavorStr):
        return ThawFlavor(flavorStr)
register(api_flavor)

class api_flavorList:
    name = 'flavorList'

    @staticmethod
    def __freeze__(flavorList):
        return [ x.freeze() for x in flavorList ]

    @staticmethod
    def __thaw__(frozenList):
        return [ ThawFlavor(x) for x in frozenList ]
register(api_flavorList)

class api_dependencyList:
    name = 'dependencyList'

    @staticmethod
    def __freeze__(depList):
        return [ x.freeze() for x in depList ]

    @staticmethod
    def __thaw__(depList):
        return [ ThawDependencySet(x) for x in depList ]
register(api_dependencyList)

class api_dependencyMissingList:
    name = 'dependencyMissingList'

    @staticmethod
    def __freeze__(depList):
        return [ (isCross, (freeze('troveTuple', x[0]), x[1].freeze())) for isCross,x in depList ]

    @staticmethod
    def __thaw__(depList):
        return [ (isCross, (thaw('troveTuple', x[0]), ThawDependencySet(x[1])))
                        for isCross, x in depList ]
register(api_dependencyMissingList)



class api_set:
    name = 'set'

    @staticmethod
    def __freeze__(item):
        return [ x for x in item ]

    @staticmethod
    def __thaw__(item):
        return set(item)
register(api_set)


class api_manual:
    name = 'manual'

    @staticmethod
    def __freeze__(item):
        return item

    @staticmethod
    def __thaw__(item):
        return item
register(api_manual)

def api_freezable(itemType):
    """ Wraps around another object that provides the freeze/thaw
        mechanism as methods.
    """
    class _api_freezable:

        name = itemType.__name__

        @staticmethod
        def __freeze__(item):
            return item.__freeze__()

        @staticmethod
        def __thaw__(item):
            return itemType.__thaw__(item)

    return _api_freezable

def register_freezable_classmap(itemName, itemClass):
    if itemName not in apitypes:
        class _api_freezable:

            name = itemName

            typeMap = {}

            @staticmethod
            def __freeze__(item):
                return (item.__class__.__name__, item.__freeze__())

            @classmethod
            def __thaw__(class_, item):
                return class_.typeMap[item[0]].__thaw__(item[1])
        apitypes[itemName] = _api_freezable

    freezeClass = apitypes[itemName]
    freezeClass.typeMap[itemClass.__name__] = itemClass

def _thawException(val):
    return RuntimeError('Exception from server:\n%s: %s\n%s' % tuple(val))

def _freezeException(err):
    etype = err.__class__
    ename = etype.__module__ + '.' + etype.__name__
    return ename, str(err), traceback.format_exc()
registerMethods('Exception', _freezeException, _thawException)

register(None, 'bool')
register(None, 'int')
register(None, 'str')
register(None, 'float')
register(procutil.MachineInformation)
