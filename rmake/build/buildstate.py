#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

"""
Describes the basic state of a build.
"""

from rmake.build import buildtrove


class AbstractBuildState(object):

    def __init__(self, sourceTroves):
        self.troves = []
        self.trovesByNVF = {}

        self.states = dict((x, set()) for x in buildtrove.TroveState.by_value)
        self.statesByTrove = {}
        self.addTroves(sourceTroves)

    def addTroves(self, sourceTroves):
        self.troves.extend(sourceTroves)
        for sourceTrove in sourceTroves:
            self.trovesByNVF[sourceTrove.getNameVersionFlavor(True)] = sourceTrove
            self.states[sourceTrove.state].add(sourceTrove)
            self.statesByTrove[sourceTrove.getNameVersionFlavor(True)] = sourceTrove.state

    def getTrove(self, name, version, flavor, context=''):
        return self.trovesByNVF[name, version, flavor, context]

    def _setState(self, sourceTrove, newState):
        nvf = sourceTrove.getNameVersionFlavor(True)
        oldState = self.statesByTrove[nvf]
        self.states[oldState].discard(sourceTrove)
        self.statesByTrove[nvf] = newState
        self.states[newState].add(sourceTrove)

    def getBuildableTroves(self):
        return self.states[buildtrove.TroveState.BUILDABLE]

    def getBuildingTroves(self):
        return self.states[buildtrove.TroveState.BUILDING]

    def getBuiltTroves(self):
        return self.states[buildtrove.TroveState.BUILT]

    def getDuplicateTroves(self):
        return self.states[buildtrove.TroveState.DUPLICATE]

    def getPreparedTroves(self):
        return self.states[buildtrove.TroveState.PREPARED]

    def getFailedTroves(self):
        return self.states[buildtrove.TroveState.FAILED] | self.states[buildtrove.TroveState.UNBUILDABLE]

    def jobFinished(self):
        return set(self.troves) == (self.getBuiltTroves()
                                    | self.getDuplicateTroves()
                                    | self.getPreparedTroves()
                                    | self.getFailedTroves())
                                            
    def jobPassed(self):
        return (set(self.troves) == (set(self.getBuiltTroves())
                                     | set(self.getDuplicateTroves()
                                     | set(self.getPreparedTroves()))))

    def isUnbuilt(self, trove):
        return (trove in self.states[buildtrove.TroveState.INIT]
                or trove in self.states[buildtrove.TroveState.BUILDABLE]
                or trove in self.states[buildtrove.TroveState.BUILDING]
                or trove in self.states[buildtrove.TroveState.PREPARING]
                or trove in self.states[buildtrove.TroveState.RESOLVING]
                or trove in self.states[buildtrove.TroveState.PREBUILT]
                or trove in self.states[buildtrove.TroveState.WAITING])

    def isBuilt(self, trove):
        return trove in self.states[buildtrove.TroveState.BUILT]
