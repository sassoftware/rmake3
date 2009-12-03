#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

python_files = *.py
dist_files = Makefile $(python_files) pycap.c pycompat.h

all: default-all pycapmodule.so

clean: default-clean
	rm -f pycapmodule.so

dist: default-dist

install: all pyfiles-install pycapmodule.so
	install -D -m0755 pycapmodule.so $(DESTDIR)$(sitedir)/$(DIR)/pycapmodule.so


pycapmodule.so: pycap.c pycompat.h
	gcc -shared -rdynamic -I/usr/include/python$(PYVERSION) pycap.c -o pycapmodule.so -g -Wall -lcap -fPIC

include ../../Make.rules
