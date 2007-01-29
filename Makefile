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

all: default-subdirs default-all

export TOPDIR = $(shell pwd)
export DISTDIR = $(TOPDIR)/rmake-$(VERSION)

SUBDIRS=rmake commands extra man

extra_files = \
	Make.rules 		\
	Makefile		\
	Make.defs		\
	NEWS			\
	LICENSE

dist_files = $(extra_files)

.PHONY: clean dist install subdirs

subdirs: default-subdirs

install: install-subdirs

clean: clean-subdirs default-clean

extra/rmake.recipe:
	cd extra; $(MAKE) rmake.recipe

infoccs: info-rmake-1.ccs info-rmake-chroot-1.ccs

info-rmake-1.ccs:
	cvc cook extra/info-rmake.recipe

info-rmake-chroot-1.ccs:
	cvc cook extra/info-rmake-chroot.recipe

ccs: dist extra/rmake.recipe infoccs
	rm -f rmake*.ccs
	rm -f extra/rmake.recipe
	cd extra;  $(MAKE) rmake.recipe
	cvc cook extra/rmake.recipe

dist:
	if ! grep "^Changes in $(VERSION)" NEWS > /dev/null 2>&1; then \
		echo "no NEWS entry"; \
		exit 1; \
	fi
	$(MAKE) forcedist


archive: $(dist_files)
	rm -rf $(DISTDIR)
	mkdir $(DISTDIR)
	for d in $(SUBDIRS); do make -C $$d DIR=$$d dist || exit 1; done
	for f in $(dist_files); do \
		mkdir -p $(DISTDIR)/`dirname $$f`; \
		cp -a $$f $(DISTDIR)/$$f; \
	done; \
	tar cjf $(DISTDIR).tar.bz2 `basename $(DISTDIR)`

sanitycheck: archive
	@echo "=== sanity building/testing rmake ==="; \
	cd $(DISTDIR); \
	make > /dev/null || exit 1; \
	./bin/rmake --version --skip-default-config > /dev/null || echo "RMAKE DOES NOT WORK" || exit 1; \
	cd -; \
	rm -rf $(DISTDIR)

forcedist: archive sanitycheck

tag:
	hg tag rmake-$(VERSION)

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
