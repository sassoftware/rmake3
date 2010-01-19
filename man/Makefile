#
# Copyright (c) 2006-2009 rPath, Inc.
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

man_files = \
	rmake.1	\
	rmake-server.8 \
	rmake-multinode.1 \
	rmake-multinode.8 \
	rmake-node.8

extra_dist = Makefile

dist_files = $(man_files) $(extra_dist)

all: default-all

install-mkdirs: install-client-mkdirs
	mkdir -p $(DESTDIR)$(mandir)/man8

install-client-mkdirs:
	mkdir -p $(DESTDIR)$(mandir)/man1

install-client: install-client-mkdirs
	install -m 644 rmake.1 rmake-multinode.1 $(DESTDIR)$(mandir)/man1

install: install-mkdirs install-client
	install -m 644 rmake-server.8 rmake-multinode.8 rmake-node.8 $(DESTDIR)$(mandir)/man8

dist: default-dist

clean: default-clean

include ../Make.rules
include ../Make.defs
