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
