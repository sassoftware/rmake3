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
