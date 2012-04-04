#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
# All Rights Reserved
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
