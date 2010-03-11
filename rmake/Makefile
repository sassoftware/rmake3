#
# Copyright (c) 2006-2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

generated_files = constants.py
install_files = $(wildcard *.py) $(generated_files)

override DEST = $(sitedir)/rmake

SUBDIRS = build cmdline db lib messagebus node server worker

all: $(generated_files) default-build

install: $(generated_files) default-install compile-python

clean: default-clean

constants.py: constants.py.in ../Makefile ../Make.defs Makefile
	sed -e s,@version@,$(VERSION),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	$< > $@


include ../Make.rules
include ../Make.defs

# vim: set sts=8 sw=8 noexpandtab filetype=make :
