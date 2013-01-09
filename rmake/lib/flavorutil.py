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

def getArchFlags(flavor, getTarget=True, withFlags=True):
    archFlavor = Flavor()
    flavorInsSet = flavor.getDepClasses().get(deps.DEP_CLASS_IS, None)
    if flavorInsSet is not None:
        for insSet in flavorInsSet.getDeps():
            if not withFlags:
                insSet = deps.Dependency(insSet.name)
            archFlavor.addDep(deps.InstructionSetDependency, insSet)
    if not getTarget:
        return archFlavor

    flavorInsSet = flavor.getDepClasses().get(deps.DEP_CLASS_TARGET_IS, None)
    if flavorInsSet is not None:
        for insSet in flavorInsSet.getDeps():
            if not withFlags:
                insSet = deps.Dependency(insSet.name)
            archFlavor.addDep(deps.TargetInstructionSetDependency, insSet)
    return archFlavor

crossFlavor = deps.parseFlavor('cross')
def getCrossCompile(flavor):
    flavorTargetSet = flavor.getDepClasses().get(deps.DEP_CLASS_TARGET_IS, None)
    if flavorTargetSet is None:
        return None

    targetFlavor = Flavor()
    for insSet in flavorTargetSet.getDeps():
        targetFlavor.addDep(deps.InstructionSetDependency, insSet)
    isCrossTool = flavor.stronglySatisfies(crossFlavor)
    return None, targetFlavor, isCrossTool

def isCrossCompiler(flavor):
    return hasTarget(flavor) and flavor.stronglySatisfies(crossFlavor)

def getArchMacros(arch):
    return {}

def getArch(flavor):
    flags = getFlavorUseFlags(flavor)
    if 'x86_64' in flags['Arch']:
        return 'x86_64'
    if 'x86' in flags['Arch']:
        return 'x86'
    if 'ppc' in flags['Arch']:
        return 'ppc'
    if 's390' in flags['Arch']:
        return 's390'
    if 'mips' in flags['Arch']:
        return 'mips'
    return None

setArchOk = {'x86_64'  : ['x86'],
             'sparc64' : ['sparc'],
             's390x'   : ['s390'],
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

if hasattr(arch, 'getMajorArch'):
    def getTargetArch(flavor, currentArch = None):
        if currentArch is None:
            currentArchName = arch.getMajorArch(arch.currentArch[0]).name
        else:
            currentArchName = arch.getMajorArch(currentArch.iterDepsByClass(
                                        deps.InstructionSetDependency)).name
        setArch = False
        targetArch = arch.getMajorArch(flavor.iterDepsByClass(
                                       deps.InstructionSetDependency))
        if not targetArch:
            return False, None
        targetArchName = targetArch.name
        if targetArchName != currentArchName:
            if targetArchName in setArchOk.get(currentArchName, []):
                setArch = True
            return setArch, targetArchName
        else:
            return False, None


def removeDepClasses(depSet, classes):
    d = depSet.__class__()
    [ d.addDep(*x) for x in depSet.iterDeps() if x[0].tag not in classes ]
    return d

def removeFileDeps(depSet):
    return removeDepClasses(depSet, [deps.DEP_CLASS_FILES])

def removeInstructionSetFlavor(depSet):
    return removeDepClasses(depSet, [deps.DEP_CLASS_IS])

def removeTargetFlavor(depSet):
    return removeDepClasses(depSet, [deps.DEP_CLASS_TARGET_IS])

def setISFromTargetFlavor(flavor):
    targetISD = deps.TargetInstructionSetDependency
    ISD = deps.InstructionSetDependency
    targetDeps = list(flavor.iterDepsByClass(targetISD))
    newFlavor = removeDepClasses(flavor, [ISD.tag, targetISD.tag])
    for dep in targetDeps:
        newFlavor.addDep(ISD, dep)
    return newFlavor

def hasTarget(flavor):
    return flavor.hasDepClass(deps.TargetInstructionSetDependency)

def getBuiltFlavor(flavor):
    if not hasTarget(flavor):
        majorArch = getTargetArch(flavor)[1]
        if majorArch:
            f = deps.Flavor()
            f.addDep(deps.InstructionSetDependency, deps.Dependency(majorArch))
            flavor = deps.overrideFlavor(flavor, f)
        return flavor
    if flavor.stronglySatisfies(crossFlavor):
        return flavor
    return setISFromTargetFlavor(flavor)

def getSysRootFlavor(flavor):
    assert(hasTarget(flavor))
    return setISFromTargetFlavor(flavor)

def getSysRootPath(flavor):
    # FIXME: if we wanted to get this exactly right, we'd have to load the 
    # macros from /etc/macros and use those values for sysroot. 
    # Best would be to do that at the same time as we load the recipe itself
    # and store it w/ the trove, because otherwise it's misleading.
    if hasTarget(flavor):
        flavor = getSysRootFlavor(flavor)
    use.setBuildFlagsFromFlavor(None, flavor, error=False)
    target = '%s-unknown-linux' % use.Arch._getMacro('targetarch')
    return '/opt/cross-target-%s/sys-root' % target
