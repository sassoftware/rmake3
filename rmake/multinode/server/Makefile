python_files = $(wildcard *.py)
dist_files = Makefile $(python_files)


all: default-subdirs default-all

clean: clean-subdirs default-clean

install: all pyfiles-install install-subdirs default-install

dist: default-dist

include ../../../Make.rules
