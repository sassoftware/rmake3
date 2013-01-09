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


python_files = __init__.py errors.py compat.py failure.py

dist_files = Makefile constants.py.in $(python_files)

SUBDIRS = build cmdline db lib messagebus multinode node server plugins subscribers worker

all: default-subdirs default-all constants.py

constants.py: constants.py.in ../Makefile ../Make.defs Makefile
	sed -e s,@version@,$(VERSION),g \
	    -e s,@changeset@,$(CHANGESET),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	    -e s,@apiMajorVersion@,$(API_MAJOR_VERSION),g \
	    -e s,@apiMinorVersion@,$(API_MINOR_VERSION),g \
	    -e s,@libexecdir@,$(libexecdir),g \
	$< > $@

install-client: install

install: all install-subdirs pyfiles-install default-install
	install constants.py $(DESTDIR)$(rmakedir)/constants.py
	$(PYTHON) -c "import compileall; compileall.compile_dir('$(DESTDIR)$(rmakedir)', ddir='$(rmakedir)', quiet=1)"
	$(PYTHON) -OO -c "import compileall; compileall.compile_dir('$(DESTDIR)$(rmakedir)', ddir='$(rmakedir)', quiet=1)"

dist: default-dist

clean: clean-subdirs default-clean
	rm -f constants.py

include ../Make.rules
include ../Make.defs
