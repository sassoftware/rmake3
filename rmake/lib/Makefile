#
# Copyright (c) 2006-2007, 2010 rPath, Inc.  All Rights Reserved.
#

python_files = *.py
dist_files = Makefile $(python_files) osutil.c pycap.c pycompat.h
so_targets = osutil.so pycap.so
PY_CFLAGS = $(CFLAGS) -I/usr/include/python$(PYVERSION) -g -Wall -fPIC
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
	gcc $(PY_LDFLAGS) -o $@ $+

.PHONY: -lcap

# Source requirements (headers)
pycapmodule.o osutil.o osutil_setproctitle.o: pycompat.h

# Modules
osutil.so: osutil_setproctitle.o
pycap.so: -lcap



include ../../Make.rules
