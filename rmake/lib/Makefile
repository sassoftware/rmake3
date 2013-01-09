#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
