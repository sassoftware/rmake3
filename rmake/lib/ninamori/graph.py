#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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
