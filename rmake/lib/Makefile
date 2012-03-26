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


python_files = *.py
dist_files = Makefile $(python_files) osutil.c pycap.c pycompat.h
so_targets = osutil.so pycap.so
PY_CFLAGS = $(CFLAGS) -I/usr/include/python$(PYVER) -g -Wall -fPIC
PY_LDFLAGS = $(LDFLAGS) -shared -rdynamic

all: default-all $(so_targets)

clean: default-clean

dist: default-dist

install: all pyfiles-install $(so_targets)
	mkdir -p $(DESTDIR)$(sitedir)/$(DIR)
	install -m0755 $(so_targets) $(DESTDIR)$(sitedir)/$(DIR)/

%.o : %.c
	gcc $(PY_CFLAGS) -c -o $@ $<
%.so : %.o
	gcc $(PY_LDFLAGS) -o $@ $^ $(LIBS)

# Source requirements (headers)
pycapmodule.o osutil.o osutil_setproctitle.o: pycompat.h

# Modules
osutil.so: osutil_setproctitle.o
osutil.so: LIBS = -ldl
pycap.so: LIBS = -lcap



include ../../Make.rules
