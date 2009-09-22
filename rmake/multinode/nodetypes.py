#
# Copyright (c) 2006-2009 rPath, Inc.
#
# All rights reserved.
#

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

class Dispatcher(NodeType):
    nodeType = 'DISPATCH'

class WorkerNode(NodeType):
    nodeType = 'WORKER'
    def __init__(self, name, host, slots, jobTypes, buildFlavors, loadThreshold,
                 nodeInfo, chroots, chrootLimit):
        self.name = name
        self.host = host
        self.slots = slots
        self.jobTypes = jobTypes
        self.buildFlavors = buildFlavors
        self.loadThreshold = loadThreshold
        self.nodeInfo = nodeInfo
        self.chroots = chroots
        self.chrootLimit = chrootLimit

    def freeze(self):
        d = self.__dict__.copy()
        d['buildFlavors'] = [freeze('flavor', x) for x in self.buildFlavors]
        d['nodeInfo'] = freeze('MachineInformation', self.nodeInfo)
        return self.nodeType, d

    @classmethod
    def thaw(class_, d):
        self = class_(**d)
        self.buildFlavors = [ thaw('flavor', x) for x in self.buildFlavors ]
        self.nodeInfo = thaw('MachineInformation', self.nodeInfo)
        return self

class BuildManager(NodeType):
    nodeType = 'BUILDER'

class Server(NodeType):
    nodeType = 'BUILDER'

class Chroot(NodeType):
    nodeType = 'CHROOT'

class Command(NodeType):
    nodeType = 'COMMAND'
