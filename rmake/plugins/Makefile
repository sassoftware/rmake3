#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
python_files = *.py
dist_files = Makefile $(python_files)

SUBDIRS=

all: default-subdirs default-all

clean: clean-subdirs default-clean

install: all pyfiles-install

dist: default-dist

include ../../Make.rules
