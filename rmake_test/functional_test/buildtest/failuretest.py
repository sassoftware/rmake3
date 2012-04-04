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
