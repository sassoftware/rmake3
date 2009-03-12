#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
plugin_files = *.py

all: default-subdirs default-all

SUBDIRS=messagebus multinode_client
export DIR=
DIR=.

extra_files = \
	Makefile		

dist_files = $(extra_files) $(plugin_files)

.PHONY: clean dist install subdirs

dist: default-dist

subdirs: default-subdirs

install: install-subdirs-noparent pluginfiles-install-noparent

install-client: install

clean: clean-subdirs default-clean

include ../Make.rules
include ../Make.defs

# vim: set sts=8 sw=8 noexpandtab :
