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


from rmake.lib import apiutils

class ApiUtilsTest(rmakehelp.RmakeHelper):
    def testRegisterFreezableClassmap(self):
        class Freezable(object):
            def __freeze__(self):
                return {}
            @classmethod
            def __thaw__(class_, d):
                return class_()
            
        class Foo(Freezable):
            pass
        class Bar(Freezable):
            pass

        apiutils.register_freezable_classmap('mytype', Foo)
        apiutils.register_freezable_classmap('mytype', Bar)

        assert(apiutils.thaw('mytype', 
               apiutils.freeze('mytype', Foo())).__class__ == Foo)
        assert(apiutils.thaw('mytype', 
               apiutils.freeze('mytype', Bar())).__class__ == Bar)
