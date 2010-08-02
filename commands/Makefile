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


bin_files = \
	rmake

sbin_files = \
	rmake-dispatcher \
	rmake-server \
	rmake-node \
	gencert-rmake

libexec_files = chroothelper gen-cert.sh

generated_files = config.h chroothelper.h chroothelper


all: chroothelper default-build
	mkdir -p ../bin
	for f in $(bin_files) $(sbin_files); do \
		ln -sf ../commands/rmake-wrapper ../bin/$$f; \
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

install: chroothelper
	for f in $(bin_files); do install -D -m755 $$f $(DESTDIR)$(bindir)/$$f; done
	for f in $(sbin_files); do install -D -m755 $$f $(DESTDIR)$(sbindir)/$$f; done
	for f in $(libexec_files); do install -D -m755 $$f $(DESTDIR)$(libexecdir)/rmake/$$f; done
	chmod 4755 $(DESTDIR)$(libexecdir)/rmake/chroothelper

clean: default-clean
	rm -rf ../bin


include ../Make.defs
include ../Make.rules

# vim: set sts=8 sw=8 noexpandtab :
