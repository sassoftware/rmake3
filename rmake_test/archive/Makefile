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


arch_files = arch/ppc arch/x86 arch/x86_64

use_files =	use/bootstrap\
		use/builddocs\
		use/buildtests\
		use/desktop\
		use/dietlibc\
		use/emacs\
		use/gcj\
		use/gdbm\
		use/gnome\
		use/gtk\
		use/ipv6\
		use/kde\
		use/krb\
		use/ldap\
		use/pam\
		use/pcre\
		use/perl\
		use/python\
		use/qt\
		use/readline\
		use/sasl\
		use/ssl\
		use/tcl\
		use/tk\
		use/X

dist_files = $(arch_files) $(use_files) Makefile

all: default-all

dist: default-dist

clean: default-clean

include ../../Make.rules
# vim: set sts=8 sw=8 noexpandtab :
