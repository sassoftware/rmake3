#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
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
