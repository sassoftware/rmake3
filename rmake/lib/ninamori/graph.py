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


class DirectedGraph(object):

    def __init__(self):
        self.edges = {}

    def addEdge(self, source, dest):
        self.edges.setdefault(source, {})[dest] = 1
        self.edges.setdefault(dest, {})

    def shortestPath(self, source, dest):
        if source == dest:
            return [source]
        if dest not in self.edges:
            # Node is not connected.
            return None

        # node -> distance of current best path
        distances = dict.fromkeys(self.edges, INF)
        # node -> previous node in current best path
        predecessors = dict.fromkeys(self.edges, None)
        # nodes which have not been followed yet
        unfinished = set(self.edges)

        distances[source] = 0

        while unfinished:
            # Pop the nearest unfinished node
            node = min((distances[x], x) for x in unfinished)[1]
            if distances[node] is INF:
                # No paths left to follow
                break
            unfinished.remove(node)

            if node == dest:
                # Cheapest remaining node is the target, so we're done.
                break

            # Update path costs for each child node, if better.
            new_cost = distances[node] + 1
            for edge in self.edges[node]:
                if new_cost < distances[edge]:
                    distances[edge] = new_cost
                    predecessors[edge] = node

        path = [dest]
        node = dest
        while predecessors[node] is not None:
            node = predecessors[node]
            path.append(node)

        if len(path) == 1:
            # No path found
            return None

        path.reverse()
        assert path[0] == source
        assert path[-1] == dest
        return path


class Infinity(object):
    __lt__ = __lte__ = __eq__ = lambda self, other: False
    __gt__ = __gte__ = __ne__ = lambda self, other: True
INF = Infinity()
