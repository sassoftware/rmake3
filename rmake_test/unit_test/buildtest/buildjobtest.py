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
