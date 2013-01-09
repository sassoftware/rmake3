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
Describes the basic state of a build.
"""

from rmake.build import buildtrove


class AbstractBuildState(object):

    def __init__(self, sourceTroves):
        self.troves = []
        self.trovesByNVF = {}

        self.states = dict((x, set()) for x in buildtrove.TROVE_STATE_LIST)
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
        return self.states[buildtrove.TROVE_STATE_BUILDABLE]

    def getBuildingTroves(self):
        return self.states[buildtrove.TROVE_STATE_BUILDING]

    def getBuiltTroves(self):
        return self.states[buildtrove.TROVE_STATE_BUILT]

    def getDuplicateTroves(self):
        return self.states[buildtrove.TROVE_STATE_DUPLICATE]

    def getPreparedTroves(self):
        return self.states[buildtrove.TROVE_STATE_PREPARED]

    def getFailedTroves(self):
        return self.states[buildtrove.TROVE_STATE_FAILED] | self.states[buildtrove.TROVE_STATE_UNBUILDABLE]

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
        return (trove in self.states[buildtrove.TROVE_STATE_INIT]
                or trove in self.states[buildtrove.TROVE_STATE_BUILDABLE]
                or trove in self.states[buildtrove.TROVE_STATE_BUILDING]
                or trove in self.states[buildtrove.TROVE_STATE_PREPARING]
                or trove in self.states[buildtrove.TROVE_STATE_RESOLVING]
                or trove in self.states[buildtrove.TROVE_STATE_PREBUILT]
                or trove in self.states[buildtrove.TROVE_STATE_WAITING])

    def isBuilt(self, trove):
        return trove in self.states[buildtrove.TROVE_STATE_BUILT]
