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
	rmake-node.8


all: default-build

install: default-install
	mkdir -p $(DESTDIR)$(mandir)/man{1,8}
	install -m 644 rmake.1 $(DESTDIR)$(mandir)/man1/

clean: default-clean

include ../Make.rules
include ../Make.defs

# vim: set sts=8 sw=8 noexpandtab :
