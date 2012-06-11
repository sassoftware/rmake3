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


python_files = $(wildcard *.py)
dist_files = Makefile $(python_files)

SUBDIRS = server

all: default-subdirs default-all

clean: clean-subdirs default-clean

install: all pyfiles-install install-subdirs default-install

dist: default-dist

include ../../Make.rules
