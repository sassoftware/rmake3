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


from rmake_test import rmakehelp

from testutils import mock

from rmake.build import buildstate

class BuildStateTest(rmakehelp.RmakeHelper):
    def testJobFinished(self):
        bs = buildstate.AbstractBuildState([])
        built = set([mock.MockObject()])
        failed = set([mock.MockObject()])
        duplicate = set([mock.MockObject()])
        prepared = set([mock.MockObject()])
        bs.getBuiltTroves = lambda: built
        bs.getFailedTroves = lambda: failed
        bs.getDuplicateTroves = lambda: duplicate
        bs.getPreparedTroves = lambda: prepared
        bs.troves = built | failed | duplicate | prepared
        assert(bs.jobFinished())
        assert(not bs.jobPassed())
        # add an unbuilt trove
        bs.troves |= set([mock.MockObject()])
        assert(not bs.jobFinished())
        bs.troves  = built | duplicate | prepared
        assert(bs.jobPassed())
