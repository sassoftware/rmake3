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


export VERSION=2.99.0
# This can be overridden on the command line.
export PYVER = $(shell python -c 'import sys; print sys.version[:3]')
export PKGNAME = rmake


SUBDIRS = commands extra man rmake rmake_test
export CHANGESET = $(shell ./scripts/hg-version.sh)

all: default-build
clean: default-clean
install: default-install
	if [ "$(PKGNAME)" != "rmake" ]; then \
		./scripts/rewrite_imports.py $(DESTDIR) $(PKGNAME); \
	fi
	$(MAKE) compile-python DEST=$(sitedir)/$(PKGNAME)

# Release instrumentation

version:
	sed -i 's/@NEW@/$(VERSION)/g' NEWS

show-version:
	@echo $(VERSION)

dist:
	if ! grep "^Changes in $(VERSION)" NEWS > /dev/null 2>&1; then \
		echo "no NEWS entry"; \
		exit 1; \
	fi
	$(MAKE) forcedist

forcedist: archive sanitycheck

archive:
	hg archive -t tbz2 -r rmake-$(VERSION) rmake-$(VERSION).tar.bz2

sanitycheck: archive
	@echo "=== sanity building/testing rmake ==="; \
	rm -rf rmake-$(VERSION); \
	tar xjf rmake-$(VERSION).tar.bz2; \
	cd rmake-$(VERSION); \
	make > /dev/null || exit 1; \
	./bin/rmake --version --skip-default-config > /dev/null || echo "RMAKE DOES NOT WORK" || exit 1; \
	cd -; \
	rm -rf rmake-$(VERSION)

tag:
	hg tag -f rmake-$(VERSION)

test: all
	if [ `id -u` ] ; then \
		if [ -f /usr/bin/sudo ] ; then \
			SUDO="sudo bash -c"; \
		else \
			SUDO="su -c" ;\
		fi; \
	else \
		SUDO=bash -c ;\
	fi ;\
	$${SUDO} 'chown root.root commands/chroothelper; \
		  chmod 4755 commands/chroothelper'

rmake3:
	# for testing only -- create a 'rmake3' directory with all the modules
	# mangled to refer to rmake3. This is similar to how the 'rmake3'
	# recipe works.
	rm -rf altroot rmake3
	$(MAKE) install DESTDIR=`pwd`/altroot PKGNAME=rmake3 NO_COMPILE=1 prefix=/opt/rmake3 libdir=/usr/lib64
	mv altroot/usr/lib64/python*/site-packages/rmake3 .
	python -mcompileall -f `pwd`/rmake3
	rm -rf altroot


.PHONY: rmake3

include Make.rules
include Make.defs

# vim: set sts=8 sw=8 noexpandtab filetype=make :
