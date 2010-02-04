#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

python_files = *.py
dist_files = Makefile $(python_files) osutil.c pycap.c pycompat.h
so_targets = osutil.so pycapmodule.so
PY_CFLAGS = $(CFLAGS) -shared -rdynamic -I/usr/include/python$(PYVERSION) -g -Wall -fPIC

all: default-all $(so_targets)

clean: default-clean
	rm -f $(so_targets)

dist: default-dist

install: all pyfiles-install $(so_targets)
	mkdir -p $(DESTDIR)$(sitedir)/$(DIR)
	install -m0755 $(so_targets) $(DESTDIR)$(sitedir)/$(DIR)/


osutil.so: osutil.c pycompat.h
	gcc $(PY_CFLAGS) -o $@ $<
pycapmodule.so: pycap.c pycompat.h
	gcc $(PY_CFLAGS) -lcap -o $@ $<

include ../../Make.rules
