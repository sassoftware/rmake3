#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

TOPDIR=..

bin_files = \
	rmake

sbin_files = \
	rmake-messagebus \
	rmake-server \
	gencert-rmake

extra_dist = Makefile rmake-wrapper chroothelper.c chroothelper.h.in gen-cert.sh

dist_files = $(bin_files) $(extra_dist) $(sbin_files)

libexec_files = chroothelper gen-cert.sh

all: default-all chroothelper
	mkdir -p $(TOPDIR)/bin
	install -m755 rmake-wrapper $(TOPDIR)/bin/rmake-wrapper
	for f in $(bin_files) $(sbin_files); do \
		ln -sf rmake-wrapper $(TOPDIR)/bin/$$f; \
	done

config.h:
	if readelf -s /lib*/libcap.so | grep -q cap_set_file ; then \
		echo '#define _HAVE_CAP_SET_FILE 1' > $@ ; \
	else \
		: > $@ ; \
	fi

chroothelper.h: chroothelper.h.in ../Make.defs
	sed -e s,@version@,$(VERSION),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@rmakegroup@,$(RMAKE_GROUP),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootgroup@,$(CHROOT_GROUP),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	$< > $@

chroothelper: chroothelper.c chroothelper.h config.h
	gcc -Wall -O2 -g -o chroothelper chroothelper.c -lcap

install-mkdirs: install-client-mkdirs
	mkdir -p $(DESTDIR)$(sbindir)
	mkdir -p $(DESTDIR)/$(libexecdir)

install-client-mkdirs:
	mkdir -p $(DESTDIR)$(bindir)

install-client: install-client-mkdirs
	for f in $(bin_files); do \
		install -m755 $$f $(DESTDIR)$(bindir)/$$f; \
	done

install: install-mkdirs install-client
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
	rm -f config.h
	rm -f chroothelper chroothelper.h
	rm -rf $(TOPDIR)/bin

include $(TOPDIR)/Make.rules
include $(TOPDIR)/Make.defs

# vim: set sts=8 sw=8 noexpandtab :
