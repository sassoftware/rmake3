#!/usr/bin/python
#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import os
import re
import stat
import sys

IMPORT_RE = re.compile('^(\s*import\s+)rmake\s*($|[.,].*$)')
FROM_RE = re.compile('^(\s*from\s+)rmake([. ].*)$')


def do_file(path, mod_base):
    st = os.stat(path)
    fobj = open(path)
    n = 0
    first = None
    if not path.endswith('.py'):
        first = fobj.readline()
        if not first.startswith('#!/usr/bin/python'):
            print 'SKIP', path
            return
    print 'MUNGE', path
    fnew = open(path + '.tmp', 'w')
    if first is not None:
        fnew.write(first)
        n += 1
    for line in fobj:
        n += 1
        m = FROM_RE.match(line)
        if m:
            fromtxt, modsuffix = m.groups()
            print >> fnew, fromtxt + mod_base + modsuffix
            continue
        m = IMPORT_RE.match(line)
        if m:
            print >> sys.stderr
            print >> sys.stderr, "%s:%s" % (path, n)
            print >> sys.stderr, line.rstrip()
            sys.exit("Can't rewrite flat imports")
        fnew.write(line)
    fobj.close()
    fnew.close()
    os.rename(path + '.tmp', path)
    os.utime(path, (st.st_atime, st.st_mtime))
    os.chmod(path, stat.S_IMODE(st.st_mode))


def main():
    root, mod_base = sys.argv[1:]

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        for filename in filenames:
            do_file(os.path.join(dirpath, filename), mod_base)


if __name__ == '__main__':
    main()
