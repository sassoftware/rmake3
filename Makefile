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
	echo $(VERSION)

dist:
	if ! grep "^Changes in $(VERSION)" NEWS > /dev/null 2>&1; then \
		echo "no NEWS entry"; \
		exit 1; \
	fi
	$(MAKE) forcedist

forcedist: archive sanitycheck

archive: $(dist_files)
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
