#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
python_files = *.py

dist_files = Makefile $(python_files)

SUBDIRS=

all: default-subdirs default-all

install: all install-subdirs pyfiles-install default-install
	$(PYTHON) -c "import compileall; compileall.compile_dir('$(DESTDIR)$(sitedir)/rmake/node', ddir='$(sitedir)/rmake/node', quiet=1)"
	$(PYTHON) -OO -c "import compileall; compileall.compile_dir('$(DESTDIR)$(sitedir)/rmake/node', ddir='$(sitedir)/rmake/node', quiet=1)"


dist: default-dist

clean: clean-subdirs default-clean

include ../../Make.rules
include ../../Make.defs
# vim: set sts=8 sw=8 noexpandtab :
