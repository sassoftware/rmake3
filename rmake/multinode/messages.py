
from rmake.messagebus import messages
from rmake.messagebus.messages import *

from rmake.multinode import nodetypes

from rmake.lib.apiutils import thaw, freeze


class RegisterNodeMessage(messages.Message):
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

class EventList(messages.Message):
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
