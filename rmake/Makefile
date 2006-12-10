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

python_files = __init__.py errors.py compat.py

dist_files = Makefile constants.py.in $(python_files)

SUBDIRS = build cmdline db lib server plugins subscribers

all: default-subdirs default-all constants.py

constants.py: constants.py.in ../Makefile ../Make.defs Makefile
	sed -e s,@version@,$(VERSION),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	    -e s,@libexecdir@,$(libexecdir),g \
	$< > $@

install: all install-subdirs pyfiles-install default-install
	$(PYTHON) -c "import compileall; compileall.compile_dir('$(DESTDIR)$(rmakedir)', ddir='$(rmakedir)', quiet=1)"
	$(PYTHON) -OO -c "import compileall; compileall.compile_dir('$(DESTDIR)$(rmakedir)', ddir='$(rmakedir)', quiet=1)"
	install constants.py $(DESTDIR)$(rmakedir)/constants.py

dist: default-dist

clean: clean-subdirs default-clean
	rm -f constants.py

include ../Make.rules
include ../Make.defs
