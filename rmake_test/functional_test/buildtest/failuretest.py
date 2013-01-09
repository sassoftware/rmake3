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

from conary.deps import deps

from rmake import failure
from rmake.lib import apiutils

class FailureTest(rmakehelp.RmakeHelper):
    def testFailureReasons(self):
        def _freeze(failureReason):
            rv = apiutils.freeze('FailureReason', failureReason)
            assert(isinstance(rv[0], int))
            assert(isinstance(rv[1], str))
            return rv

        def _thaw(frz):
            return apiutils.thaw('FailureReason', frz)

        f = failure.BuildFailed('foo')
        assert(str(f) == 'Failed while building: foo')
        assert(_thaw(_freeze(f)) == f)
        f = failure.MissingBuildreqs([
                                ('foo:runtime', '', deps.parseFlavor('cross,bar.core'))])
        assert(_thaw(_freeze(f)) == f)
        assert(str(f) == 'Could not satisfy build requirements: foo:runtime=[bar.core,cross]')

        trv = self.addComponent('blah:run', '1.0')
        f = failure.MissingDependencies([(trv.getNameVersionFlavor(),
                              deps.parseDep('trove: blam trove:foo'))])
        assert(_thaw(_freeze(f)) == f)
        assert(str(f) == 'Could not satisfy dependencies:\n'
                         '    blah:run=/localhost@rpl:linux/1.0-1-1[] requires:\n'
                         '\ttrove: blam\n'
                         '\ttrove: foo')
        f = failure.InternalError(['foo', 'bar'])
        assert(_thaw(_freeze(f)) == f)
        f = failure.Stopped('Blah')
        assert(_thaw(_freeze(f)) == f)
