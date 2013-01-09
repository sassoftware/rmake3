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
