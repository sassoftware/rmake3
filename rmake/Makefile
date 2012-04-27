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


python_files = __init__.py errors.py compat.py failure.py

dist_files = Makefile constants.py.in $(python_files)

SUBDIRS = build cmdline db lib messagebus multinode node server plugins subscribers worker

all: default-subdirs default-all constants.py

constants.py: constants.py.in ../Makefile ../Make.defs Makefile
	sed -e s,@version@,$(VERSION),g \
	    -e s,@changeset@,$(CHANGESET),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	    -e s,@apiMajorVersion@,$(API_MAJOR_VERSION),g \
	    -e s,@apiMinorVersion@,$(API_MINOR_VERSION),g \
	    -e s,@libexecdir@,$(libexecdir),g \
	$< > $@

install-client: install

install: all install-subdirs pyfiles-install default-install
	install constants.py $(DESTDIR)$(rmakedir)/constants.py
	$(PYTHON) -c "import compileall; compileall.compile_dir('$(DESTDIR)$(rmakedir)', ddir='$(rmakedir)', quiet=1)"
	$(PYTHON) -OO -c "import compileall; compileall.compile_dir('$(DESTDIR)$(rmakedir)', ddir='$(rmakedir)', quiet=1)"

dist: default-dist

clean: clean-subdirs default-clean
	rm -f constants.py

include ../Make.rules
include ../Make.defs
