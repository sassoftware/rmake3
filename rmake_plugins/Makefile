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


plugin_files = *.py

all: default-subdirs default-all

SUBDIRS = multinode_client multinode
export DIR=
DIR=.

extra_files = \
	Makefile		

dist_files = $(extra_files) $(plugin_files)

.PHONY: clean dist install subdirs

dist: default-dist

subdirs: default-subdirs

install: install-subdirs-noparent pluginfiles-install-noparent

install-client: install

clean: clean-subdirs default-clean

include ../Make.rules
include ../Make.defs

# vim: set sts=8 sw=8 noexpandtab :
