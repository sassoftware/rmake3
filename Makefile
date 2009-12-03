#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

all: default-subdirs default-all

export TOPDIR = $(shell pwd)
export DISTDIR = $(TOPDIR)/rmake-$(VERSION)

SUBDIRS=rmake commands extra man rmake_plugins

extra_files = \
	Make.rules 		\
	Makefile		\
	Make.defs		\
	NEWS			\
	CPL			\
	LICENSE

dist_files = $(extra_files)

.PHONY: clean dist install subdirs

subdirs: default-subdirs

install: install-subdirs 
	make -C rmake_plugins install || exit 1

install-client: install-client-subdirs

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


archive: $(dist_files)
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
