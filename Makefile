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


all: default-subdirs default-all

export TOPDIR = $(shell pwd)
export DISTDIR = $(TOPDIR)/rmake-$(VERSION)
export CHANGESET = $(shell ./scripts/hg-version.sh)
SUBDIRS=rmake commands extra man rmake_plugins

.PHONY: clean dist install subdirs

subdirs: default-subdirs

install: install-subdirs 
	make -C rmake_plugins install || exit 1

install-client: install-client-subdirs

clean: clean-subdirs default-clean

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


archive:
	hg archive -t tbz2 -r rmake-$(VERSION) rmake-$(VERSION).tar.bz2

sanitycheck: archive
	@echo "=== sanity building/testing rmake ==="; \
	rm -rf $(DISTDIR); \
	tar xjf rmake-$(VERSION).tar.bz2; \
	cd $(DISTDIR); \
	make > /dev/null || exit 1; \
	./bin/rmake --version --skip-default-config > /dev/null || echo "RMAKE DOES NOT WORK" || exit 1; \
	cd -; \
	rm -rf $(DISTDIR)

forcedist: archive sanitycheck

tag:
	hg tag -f rmake-$(VERSION)

clean: clean-subdirs default-clean

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

include Make.rules
include Make.defs
 
# vim: set sts=8 sw=8 noexpandtab :
