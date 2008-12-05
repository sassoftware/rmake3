import inspect
import sys
import types

from rmake.lib.apiutils import thaw, freeze

class NodeType(object):
    nodeType = 'UNKNOWN'
    def __init__(self):
        pass

    def freeze(self):
        return (self.nodeType, self.__dict__)

    @classmethod
    def thaw(class_, d):
        return class_(**d)

class Client(NodeType):
    nodeType = 'CLIENT'

_nodeTypes = {}
def registerNodeTypes(moduleName):
    global _nodeTypes
    for item in sys.modules[moduleName].__dict__.values():
        if inspect.isclass(item) and issubclass(item, NodeType):
            _nodeTypes[item.nodeType] = item
registerNodeTypes(__name__)

def registerNodeType(class_):
    _nodeTypes[class_.nodeType] = class_

def thawNodeType(info):
    nodeType = info[0]
    return _nodeTypes[nodeType].thaw(info[1])
