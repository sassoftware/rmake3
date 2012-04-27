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
