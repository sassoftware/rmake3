#!/usr/bin/python
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
