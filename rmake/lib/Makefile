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

so_targets = osutil.so pycap.so
install_files = $(wildcard *.py) $(so_targets)

LDFLAGS := $(LDFLAGS) -lcap

SUBDIRS = proc_pool twisted_extras


all: $(so_targets) default-build

clean: default-clean
	find ninamori -name \*.pyc -delete

install: $(so_targets) default-install
	cp -r ninamori $(DESTDIR)$(DEST)/

# Use this to regenerate the embedded ninamori implementation.
# See http://bitbucket.org/gxti/ninamori/
embed:
ifdef NINAMORI_PATH
	rm -Rf ninamori ninamori-tmp
	mkdir ninamori
	hg parents -R $(NINAMORI_PATH) --template '{node}\n' > ninamori/.hgnode
	hg archive -R $(NINAMORI_PATH) -t files -r `cat ninamori/.hgnode` ninamori-tmp
	python ninamori-tmp/embed.py ninamori-tmp/ninamori/ ninamori/ rmake.lib
	hg addremove ninamori
	rm -Rf ninamori-tmp
else
	@echo "Please set NINAMORI_PATH" && exit 1
endif


# Source requirements (headers)
pycapmodule.o osutil.o osutil_setproctitle.o: pycompat.h

# Modules
osutil.so: osutil_setproctitle.o
pycap.so:


include ../../Make.defs
include ../../Make.rules

# vim: set sts=8 sw=8 noexpandtab filetype=make :
