import inspect
import sys
import types

from rmake.lib.apiutils import thaw, freeze


_nodeTypes = {}
class _NodeTypeRegistrar(type):
    def __init__(self, name, bases, dict):
        type.__init__(self, name, bases, dict)
        _nodeTypes[self.nodeType] = self


class NodeType(object):
    __metaclass__ = _NodeTypeRegistrar
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

def thawNodeType(info):
    nodeType = info[0]
    return _nodeTypes[nodeType].thaw(info[1])
