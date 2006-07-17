#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
rMake, build utility for conary
"""

# add backwards compatibility for conary < 1.0.19
# this can be removed once we reach conary 1.1
from conary.deps import deps
if not hasattr(deps, 'ThawFlavor'):
    deps.Flavor = deps.DependencySet
    deps.ThawFlavor = deps.ThawDependencySet
    deps.DependencySet.isEmpty = lambda self: not self
