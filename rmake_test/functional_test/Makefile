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


MYDIR=$(shell basename `pwd`)

test:
	cd .. && ./testsuite.py $(MYDIR)

debug:
	cd .. && ./testsuite.py $(MYDIR) --debug

coverage:
	rm -rf annotate;
	cd .. && ./testsuite.py $(MYDIR) --coverage
	mv ../annotate .
