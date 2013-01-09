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


from conary.deps import deps

from rmake.build import buildcfg, buildtrove
from rmake.lib.apiutils import thaw, freeze
from rmake.messagebus.messages import *
from rmake.multinode import nodetypes


class RegisterNodeMessage(Message):
    """
        Alert others to the addition of a new node to the messagebus.
    """
    messageType = 'REGISTER_NODE'

    def set(self, node):
        self.headers.nodeType = node.nodeType
        self.payload.node = node

    def getNode(self):
        return self.payload.node

    def payloadToDict(self):
        return dict(node=self.payload.node.freeze())

    def loadPayloadFromDict(self, d):
        self.payload.node = nodetypes.thawNodeType(d['node'])

class EventList(Message):
    messageType = 'EVENT'

    def set(self, jobId, eventList):
        self.headers.jobId = str(jobId)
        self.payload.eventList = eventList

    def getJobId(self):
        return int(self.headers.jobId)

    def getEventList(self):
        return self.payload.eventList

    def payloadToDict(self):
        return dict(eventList=freeze('EventList', self.payload.eventList))

    def loadPayloadFromDict(self, d):
        self._payload.__dict__.update(d)
        self.payload.eventList = thaw('EventList', self.payload.eventList)


class NodeInfo(Message):
    """
        Node status message
    """
    messageType = 'NODE_INFO'

    def set(self, nodeInfo, commands):
        self.payload.nodeInfo = nodeInfo
        self.payload.commands = commands

    def getNodeInfo(self):
        return self.payload.nodeInfo

    def getCommands(self):
        return self.payload.commands

    def payloadToDict(self):
        d = dict(nodeInfo=freeze('MachineInformation', self.payload.nodeInfo),
                 commands=self.payload.commands)
        return d

    def loadPayloadFromDict(self, d):
        self._payload.__dict__.update(d)
        self.payload.nodeInfo = thaw('MachineInformation',
                                     self.payload.nodeInfo)

class _Command(Message):
    """
        Superclass for command requests.
    """
    def set(self, commandId, jobId, targetNode=''):
        self.headers.commandId = commandId
        self.headers.jobId = jobId
        # target node can be empty, in which case the command has
        # not been assigned to a node yet and needs to be handled by the
        # dispatcher.
        self.headers.targetNode = targetNode

    def requiresChroot(self):
        return False

    def getTargetNode(self):
        return self.headers.targetNode

    def setTargetNode(self, sessionId):
        self.headers.targetNode = sessionId

    def getCommandId(self):
        return self.headers.commandId

    def getJobId(self):
        return int(self.headers.jobId)

    def getRequiredFlavors(self):
        return []


class ResolveCommand(_Command):
    messageType = 'RESOLVE'

    def set(self, commandId, jobId, resolveJob, logData, targetNode=''):
        _Command.set(self, commandId, jobId, targetNode)
        self.payload.resolveJob = resolveJob
        self.payload.logData = logData

    def getTrove(self):
        return self.payload.resolveJob.getTrove()

    def getResolveJob(self):
        return self.payload.resolveJob

    def getLogData(self):
        return self.payload.logData

    def loadPayloadFromDict(self, d):
        self._payload.__dict__.update(d)
        self.payload.resolveJob = thaw('ResolveJob', self.payload.resolveJob)
        self.payload.logData = d['logData']

    def payloadToDict(self):
        return dict(resolveJob=freeze('ResolveJob', self.payload.resolveJob),
                    logData=self.payload.logData)


class LoadCommand(_Command):
    messageType = 'LOAD'

    def set(self, commandId, job, loadTroves, reposName, targetNode=''):
        _Command.set(self, commandId, job.jobId, targetNode)
        self.payload.job = job
        self.payload.loadTroves = loadTroves
        self.payload.reposName = reposName

    def getJob(self):
        return self.payload.job

    def getLoadTroves(self):
        return self.payload.loadTroves

    def getReposName(self):
        return self.payload.reposName

    def loadPayloadFromDict(self, blob):
        self._payload.__dict__.update(blob)
        self.payload.job = thaw('BuildJob', self.payload.job)
        self.payload.loadTroves = [ thaw('troveContextTuple', x)
            for x in self.payload.loadTroves ]

    def payloadToDict(self):
        job = freeze('BuildJob', self.payload.job)
        loadTroves = [ freeze('troveContextTuple', x)
            for x in self.payload.loadTroves ]
        return dict(job=job, loadTroves=loadTroves,
            reposName=self.payload.reposName)


class BuildCommand(_Command):
    messageType = 'BUILD'

    def set(self, commandId, buildCfg, jobId, trove, buildReqs, crossReqs,
            targetLabel, logData=None, bootstrapReqs=(), builtTroves=(),
            targetNode=''):
        _Command.set(self, commandId, jobId, targetNode)
        self.payload.logData = logData
        self.payload.trove = trove
        self.payload.buildCfg = buildCfg
        self.payload.buildReqs = list(buildReqs)
        self.payload.crossReqs = list(crossReqs)
        self.payload.bootstrapReqs = list(bootstrapReqs)
        self.payload.targetLabel = targetLabel
        self.payload.builtTroves = list(builtTroves)

    def getLogInfo(self):
        return self.payload.logData

    def requiresChroot(self):
        return True

    def getTrove(self):
        return self.payload.trove

    def getRequiredFlavors(self):
        if self.payload.buildReqs:
           return [ x[2][1] for x in self.payload.buildReqs ]
        return []

    def getBuildConfig(self):
        return self.payload.buildCfg

    def getBuildReqs(self):
        return self.payload.buildReqs

    def getCrossReqs(self):
        return self.payload.crossReqs

    def getBootstrapReqs(self):
        return self.payload.bootstrapReqs

    def getBuiltTroves(self):
        return self.payload.builtTroves

    def getTargetLabel(self):
        return self.payload.targetLabel

    def payloadToDict(self):
        buildCfg = freeze('BuildConfiguration', self.payload.buildCfg)
        trove = freeze('BuildTrove', self.payload.trove)
        targetLabel = freeze('label', self.payload.targetLabel)
        builtTroves = freeze('troveTupleList', self.payload.builtTroves)
        d = dict(buildCfg=buildCfg,
                 trove=trove,
                 targetLabel=targetLabel,
                 builtTroves=builtTroves,
                 logData=self.payload.logData)

        for name in ('buildReqs', 'crossReqs', 'bootstrapReqs'):
            tuples = [((x[0],) + x[2]) for x in getattr(self.payload, name)]
            d[name] = freeze('troveTupleList', tuples)

        if self.payload.logData is None:
            d['logData'] = ''
        return d

    def loadPayloadFromDict(self, d):
        self._payload.__dict__.update(d)
        self.payload.buildCfg = thaw('BuildConfiguration',
                                     self.payload.buildCfg)
        self.payload.trove = thaw('BuildTrove', self.payload.trove)
        for name in ('buildReqs', 'crossReqs', 'bootstrapReqs'):
            tuples = thaw('troveTupleList', getattr(self.payload, name))
            jobs = [(x[0], (None, None), x[1:3], False) for x in tuples]
            setattr(self.payload, name, jobs)
        self.payload.builtTroves = thaw('troveTupleList',
                                        self.payload.builtTroves)
        self.payload.targetLabel = thaw('label', self.payload.targetLabel)
        if self.payload.logData == '':
            self.payload.logData = None

class ActionCommand(_Command):

    messageType = 'ACTION'

    def set(self, commandId, commandName, buildCfg, jobId, trove, logData, 
            targetNode=''):
        _Command.set(self, commandId, jobId, targetNode)
        self.headers.commandName = commandName
        self.payload.logData = logData
        self.payload.trove = trove
        self.payload.buildCfg = buildCfg

    def getCommandName(self):
        return self.headers.commandName

    def getTrove(self):
        return self.payload.trove

    def getBuildConfig(self):
        return self.payload.buildCfg

    def getLogData(self):
        return self.payload.logData

    def payloadToDict(self):
        buildCfg = freeze('BuildConfiguration', self.payload.buildCfg)
        trove = freeze('BuildTrove', self.payload.trove)
        d = dict(buildCfg=buildCfg,
                 trove=trove,
                 logData=self.payload.logData)
        if self.payload.logData is None:
            d['logData'] = ''
        return d

    def loadPayloadFromDict(self, d):
        self._payload.__dict__.update(d)
        self.payload.buildCfg = thaw('BuildConfiguration',
                                     self.payload.buildCfg)
        self.payload.trove = thaw('BuildTrove', self.payload.trove)
        if self.payload.logData == '':
            self.payload.logData = None

class StopCommand(_Command):

    messageType = 'STOPCOMMAND'

    def set(self, commandId, jobId, targetCommandId, targetNode=''):
        _Command.set(self, commandId, jobId, targetNode)
        self.headers.commandId = commandId
        self.headers.targetCommandId = targetCommandId
        self.headers.targetNode = targetNode

    def getTargetCommandId(self):
        return self.headers.targetCommandId

class CommandStatus(Message):
    """
        Message sent to dispatcher regarding the status of a build.
    """
    messageType = 'COMMAND_STATUS'

    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    ERROR = 'ERROR'

    def set(self, commandId, status, failureReason=None):
        self.headers.commandId = commandId
        self.headers.status = status
        self.payload.failureReason = failureReason

    def isCompleted(self):
        return self.headers.status == self.COMPLETED

    def isInProgress(self):
        return self.headers.status == self.IN_PROGRESS

    def isErrored(self):
        return self.headers.status == self.ERROR

    def getFailureReason(self):
        return self.payload.failureReason

    def getCommandId(self):
        return self.headers.commandId

    def payloadToDict(self):
        if self.payload.failureReason:
            return dict(failureReason=freeze('FailureReason',
                                             self.payload.failureReason))
        else:
            return dict(failureReason=None)

    def loadPayloadFromDict(self, d):
        self._payload.__dict__.update(d)
        if self.payload.failureReason:
            self.payload.failureReason = thaw('FailureReason', self.payload.failureReason)
