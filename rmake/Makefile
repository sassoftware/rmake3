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


generated_files = constants.py
install_files = $(wildcard *.py) $(generated_files)

override DEST = $(rmakedir)

SUBDIRS = build cmdline core lib messagebus server worker

all: $(generated_files) default-build

install: $(generated_files) default-install

clean: default-clean

constants.py: constants.py.in ../Makefile ../Make.defs Makefile
	sed -e s,@version@,$(VERSION),g \
	    -e s,@changeset@,$(CHANGESET),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	$< > $@


include ../Make.rules
include ../Make.defs

# vim: set sts=8 sw=8 noexpandtab filetype=make :
