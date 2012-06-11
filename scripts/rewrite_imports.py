#!/usr/bin/python
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
