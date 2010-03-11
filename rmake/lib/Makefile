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


all: $(so_targets) default-build

clean: default-clean

install: $(so_targets) default-install


.PHONY: -lcap

# Source requirements (headers)
pycapmodule.o osutil.o osutil_setproctitle.o: pycompat.h

# Modules
osutil.so: osutil_setproctitle.o
pycap.so: -lcap


include ../../Make.defs
include ../../Make.rules

# vim: set sts=8 sw=8 noexpandtab filetype=make :
