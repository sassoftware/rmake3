#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
plugin_files = *.py

dist_files = Makefile $(plugin_files)

SUBDIRS=

all: default-subdirs default-all

install: all install-subdirs pluginfiles-install default-install

dist: default-dist

clean: clean-subdirs default-clean

include ../../Make.rules
include ../../Make.defs
