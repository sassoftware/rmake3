# -*- mode: python -*-
#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

import os
import signal
import sys
import time


#test
from conary_test import rephelp

from conary.deps import deps
from conary import versions

#rmake
from rmake.lib import apiutils
from rmake.lib.apiutils import api, api_parameters, api_return

class ApiRPCTest(rephelp.RepositoryHelper):
    def testTroveTupleList(self):
        ttl = apiutils.api_troveTupleList
        x = [ ('foo', versions.ThawVersion('/l@r:p/1.0:1-1-1'), 
                deps.parseFlavor('~!bar')) ]
        assert(ttl.__thaw__(ttl.__freeze__(x)) == x)

    def testApiDeco(self):
        @api(allowed=[1,2,3])
        def foo(bar):
            pass

        assert(foo.allowed_versions == set([0,1,2,3]))

    def testApiParametersDeco(self):
        @api_parameters(1, 'flavor')
        def foo(bar):
            pass
        assert(foo.params[1] == [apiutils.api_flavor])

    def testApiReturnDeco(self):
        @api_return(1, 'flavor')
        def foo(bar):
            pass
        assert(foo.returnType[1] is apiutils.api_flavor)


