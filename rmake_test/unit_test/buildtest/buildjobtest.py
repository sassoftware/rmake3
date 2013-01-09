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

class TestBuildJob(rmakehelp.RmakeHelper):
    def testIterTroveList(self):
        job = self.newJob(self.makeTroveTuple('foo:source'),
                          self.makeTroveTuple('bar:source'))
        trvs = dict((x.getName(), x) for x in job.iterTroves())
        assert(list(job.iterLoadableTroveList()))
        assert(list(job.iterLoadableTroveList()) == list(job.iterTroveList(True)))
        assert(list(job.iterLoadableTroves()) == list(job.iterTroves()))
        foo = trvs['foo:source']
        bar = trvs['bar:source']
        foo.isSpecial = lambda: True
        assert(list(job.iterLoadableTroves()) == [bar])
        assert(list(job.getSpecialTroves()) == [foo])


    

if __name__ == '__main__':
    testsetup.main()
