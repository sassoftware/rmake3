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



SUBDIRS = proc_pool twisted_extras

so_targets = osutil.so pycap.so
install_files = $(wildcard *.py) $(so_targets)

PY_CFLAGS = $(CFLAGS) -I/usr/include/python$(PYVER) -g -Wall -fPIC
PY_LDFLAGS := $(LDFLAGS) -lcap


all: $(so_targets) default-build

install: $(so_targets) default-install
	cp -a jabberlink ninamori $(DESTDIR)$(DEST)/

clean: default-clean
	find jabberlink ninamori -name \*.pyc -delete

%.o : %.c
	gcc $(PY_CFLAGS) -c -o $@ $<
%.so : %.o
	gcc $(PY_LDFLAGS) -o $@ $^ $(LIBS)

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
	hg log -R $(NINAMORI_PATH) -r `cat ninamori/.hgnode`
else
	@echo "Please set NINAMORI_PATH" && exit 1
endif


# Source requirements (headers)
pycapmodule.o osutil.o osutil_setproctitle.o: pycompat.h

# Modules
osutil.so: osutil_setproctitle.o
osutil.so: LIBS = -ldl
pycap.so: LIBS = -lcap


include ../../Make.defs
include ../../Make.rules

# vim: set sts=8 sw=8 noexpandtab filetype=make :
