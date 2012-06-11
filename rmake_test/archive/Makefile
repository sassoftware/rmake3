#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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
