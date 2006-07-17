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

# flavor manipulations

#
from conary.deps import arch
from conary.deps import deps
from conary.build import use
from conary.build.use import Flag, Arch, Use, LocalFlags
try:
    from conary.deps.deps import Flavor
except ImportError:
    from conary.deps.deps import DependencySet as Flavor

def getFlavorUseFlags(flavor):
    """ Convert a flavor-as-dependency set to flavor-as-use-flags.
    """
    useFlags = {}
    useFlags['Use'] = {}
    useFlags['Arch'] = {}
    useFlags['Flags'] = {}
    if flavor is None:
        return useFlags
    for depGroup in flavor.getDepClasses().values():
        if isinstance(depGroup, deps.UseDependency):
            for dep in depGroup.getDeps():
                for flag, sense in dep.flags.iteritems():
                    value = True
                    if sense in (deps.FLAG_SENSE_REQUIRED,
                                 deps.FLAG_SENSE_PREFERRED):
                        value = True
                    else:
                        value = False
                    parts = flag.split('.',1)
                    if len(parts) == 1:
                        useFlags['Use'][flag] = value
                    else:
                        name = parts[0]
                        flag = parts[1]
                        if name not in useFlags['Flags']:
                            useFlags['Flags'][name] = {} 
                        useFlags['Flags'][name][flag] = value
        elif isinstance(depGroup, deps.InstructionSetDependency):
            for dep in depGroup.getDeps():
                majarch = dep.name
                # should not be any negative major archs
                useFlags['Arch'][majarch] = {}
                for (flag, sense) in dep.flags.iteritems():
                    if sense in (deps.FLAG_SENSE_REQUIRED,
                                 deps.FLAG_SENSE_PREFERRED):
                        value = True
                    else:
                        value = False
                    useFlags['Arch'][majarch][flag] = value
    return useFlags

def getLocalFlags():
    """ Get the local flags that are currently set, so that the flags 
        created can be reset. """
    return [ x for x in LocalFlags._iterAll()]

def setLocalFlags(flags):
    """ Make the given local flags exist.  """
    for flag in flags:
        LocalFlags.__setattr__(flag._name, flag._get())

def resetLocalFlags():
    """ Delete all created local flags. """
    LocalFlags._clear()

def knownArches():
    return ('x86', 'x86_64', 'ppc', 'mips')

def isKnownArch(arch):
    return arch in knownArches()

def getArchFlags(flavor):
    archFlavor = Flavor()
    flavorInsSet = flavor.getDepClasses().get(deps.DEP_CLASS_IS, None)
    if flavorInsSet is not None:
        for insSet in flavorInsSet.getDeps():
            archFlavor.addDep(deps.InstructionSetDependency, insSet)
    return archFlavor

def getArchFlavor(arch):
    if arch in ('x86', 'i386'):
        return deps.parseFlavor('is: x86')
    elif arch == 'x86_64':
        return deps.parseFlavor('is: x86_64')
    elif arch == 'ppc':
        return deps.parseFlavor('is: ppc')
    elif arch == 'mips':
        return deps.parseFlavor('is: mips')
    assert(False)

def getArchMacros(arch):
    return {}

def setArch(flavor, arch):
    return overrideFlavor(flavor, getArchFlavor(arch))

def mergeArch(flavor, arch):
    return mergeFlavor(flavor, getArchFlavor(arch))

def mergeFlavor(flavor, newFlavor):
    flavor = flavor.copy()
    flavor.union(newFlavor)
    return flavor

def overrideFlavor(oldFlavor, newFlavor):
    flavor = oldFlavor.copy()
    if (deps.DEP_CLASS_IS in flavor.getDepClasses() 
        and deps.DEP_CLASS_IS in newFlavor.getDepClasses()):
        del flavor.members[deps.DEP_CLASS_IS]
    flavor.union(newFlavor, mergeType=deps.DEP_MERGE_TYPE_OVERRIDE)
    return flavor

def getArch(flavor):
    flags = getFlavorUseFlags(flavor)
    if 'x86_64' in flags['Arch']:
        return 'x86_64'
    if 'x86' in flags['Arch']:
        return 'x86'
    if 'ppc' in flags['Arch']:
        return 'ppc'
    if 'mips' in flags['Arch']:
        return 'mips'
    return None

def clearAllFlags():
    use._clear()

def getSubFlavors(flavor, subFlavors, name):
    mainFlags = getFlavorUseFlags(flavor)
    matchingSubFlavors = []
    for subFlavor in subFlavors:
        subFlags = getFlavorUseFlags(subFlavor)
        mainUse = mainFlags['Use']
        subUse = subFlags['Use']
        found = True
        try:
            for flag, value in subUse.iteritems():
                if mainUse[flag] != value:
                    raise KeyError
            if name in subFlags['Flags']:
                subLocal = subFlags['Flags'][name]
                mainLocal = mainFlags['Flags'][name]
                for flag, value in subLocal.iteritems():
                    if flag in mainLocal and mainLocal[flag] != value:
                        # don't complain if local flag is not set -- 
                        # we allow defaults to be used 
                        raise KeyError
            mainArch = mainFlags['Arch']
            subArch = subFlags['Arch']
            for majarch in subArch:
                if majarch not in mainArch:
                    raise KeyError
                for minarch in subArch[majarch]:
                    if minarch not in mainArch[majarch]:
                        raise KeyError
            matchingSubFlavors.append(subFlavor)
        except KeyError:
            pass
    return matchingSubFlavors

ignoredClasses = [ deps.DEP_CLASS_ABI ]

def iterDeps(flavor, ignoreABI=False):
    """ iterates through all the individual dependencies in 
        a dependency set by creating a dependency.  
    """
    for depClass in flavor.members.values():
        if ignoreABI and depClass.tag in ignoredClasses:
            continue
        for dependency in depClass.members.values():
            newDep = Flavor()
            newDep.addDep(depClass.__class__, dependency)
            yield newDep

setArchOk = {'x86_64'  : ['x86'],
             'sparc64' : ['sparc'],
             'ppc64'   : ['ppc'] }


def getTargetArch(flavor, currentArch = None):
    if currentArch is None:
        currentArch = Flavor()
        currentArch.addDep(deps.InstructionSetDependency,
                           arch.currentArch[0][0])
    setArch = False

    currentArchName = [ x.name for x in 
                  currentArch.iterDepsByClass(deps.InstructionSetDependency) ]
    assert(len(currentArchName) == 1)
    currentArchName = currentArchName[0]

    archNames = [ x.name for x in
                  flavor.iterDepsByClass(deps.InstructionSetDependency) ]
    if len(archNames) > 1:
        raise RuntimeError, 'Cannot build trove with two architectures'
    if not archNames:
        return False, None
    targetArch = archNames[0]

    if targetArch != currentArchName:
        if targetArch in setArchOk.get(currentArchName, []):
            setArch = True
        return setArch, targetArch
    else:
        return False, None
