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


generated_files = constants.py
install_files = $(wildcard *.py) $(generated_files)

override DEST = $(rmakedir)

SUBDIRS = build cmdline core lib messagebus server worker

all: $(generated_files) default-build

install: $(generated_files) default-install

clean: default-clean

constants.py: constants.py.in ../Makefile ../Make.defs Makefile
	sed -e s,@version@,$(VERSION),g \
	    -e s,@changeset@,$(CHANGESET),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	$< > $@


include ../Make.rules
include ../Make.defs

# vim: set sts=8 sw=8 noexpandtab filetype=make :
