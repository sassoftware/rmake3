#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

TOPDIR=..

bin_files = \
	rmake

sbin_files = \
	rmake-server

extra_dist = Makefile rmake-wrapper chroothelper.c chroothelper.h.in rmake-xml

dist_files = $(bin_files) $(extra_dist) $(sbin_files)

libexec_files = rmake-xml chroothelper

all: default-all chroothelper
	mkdir -p $(TOPDIR)/bin
	install -m755 rmake-wrapper $(TOPDIR)/bin/rmake-wrapper
	for f in $(bin_files) $(sbin_files); do \
		ln -sf rmake-wrapper $(TOPDIR)/bin/$$f; \
	done

chroothelper.h: chroothelper.h.in ../Make.defs
	sed -e s,@version@,$(VERSION),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@rmakegroup@,$(RMAKE_GROUP),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootgroup@,$(CHROOT_GROUP),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	$< > $@

chroothelper: chroothelper.c chroothelper.h
	gcc -Wall -O2 -g -o chroothelper chroothelper.c -lcap


install-mkdirs:
	mkdir -p $(DESTDIR)$(bindir)
	mkdir -p $(DESTDIR)$(sbindir)
	mkdir -p $(DESTDIR)/$(libexecdir)

install: install-mkdirs
	for f in $(bin_files); do \
		install -m755 $$f $(DESTDIR)$(bindir)/$$f; \
	done
	for f in $(sbin_files); do \
		install -m755 $$f $(DESTDIR)$(sbindir)/$$f; \
	done
	mkdir -p $(DESTDIR)$(libexecdir)/rmake
	for f in $(libexec_files); do \
		install -m755 $$f $(DESTDIR)$(libexecdir)/rmake/$$f; \
	done
	chmod 4755 $(DESTDIR)$(libexecdir)/rmake/chroothelper

dist: default-dist

clean: default-clean
	rm -f chroothelper chroothelper.h
	rm -rf $(TOPDIR)/bin

include $(TOPDIR)/Make.rules
include $(TOPDIR)/Make.defs
