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


bin_files = \
	rmake

sbin_files = \
	rmake-dispatcher \
	rmake-node \
	gencert-rmake

bin_targets = $(patsubst %,../bin/%,$(bin_files) $(sbin_files))

libexec_files = chroothelper gen-cert.sh

generated_files = config.h chroothelper.h chroothelper


all: chroothelper default-build $(bin_targets)


$(bin_targets): ../bin/%: rmake-wrapper
	mkdir -p ../bin
	ln -sfn ../commands/$< $@

config.h: Makefile
	if readelf -s /lib*/libcap.so | grep -q cap_set_file ; then \
		echo '#define _HAVE_CAP_SET_FILE 1' > $@ ; \
	else \
		: > $@ ; \
	fi

chroothelper.h: chroothelper.h.in ../Make.defs
	sed -e s,@version@,$(VERSION),g \
	    -e s,@rmakeuser@,$(RMAKE_USER),g \
	    -e s,@rmakegroup@,$(RMAKE_GROUP),g \
	    -e s,@chrootuser@,$(CHROOT_USER),g \
	    -e s,@chrootgroup@,$(CHROOT_GROUP),g \
	    -e s,@chrootserver@,$(CHROOT_SERVER),g \
	    -e s,@chrootrmake@,$(CHROOT_RMAKE),g \
	$< > $@

chroothelper: chroothelper.c chroothelper.h config.h
	gcc -Wall -O2 -g -o chroothelper chroothelper.c -lcap

install: chroothelper
	for f in $(bin_files); do install -D -m755 $$f $(DESTDIR)$(bindir)/$(subst rmake,$(PKGNAME),$$f); done
	for f in $(sbin_files); do install -D -m755 $$f $(DESTDIR)$(sbindir)/$(subst rmake,$(PKGNAME),$$f); done
	for f in $(libexec_files); do install -D -m755 $$f $(DESTDIR)$(libexecdir)/rmake/$$f; done
	chmod 4755 $(DESTDIR)$(libexecdir)/rmake/chroothelper

clean: default-clean
	rm -rf ../bin


include ../Make.defs
include ../Make.rules

# vim: set sts=8 sw=8 noexpandtab :
