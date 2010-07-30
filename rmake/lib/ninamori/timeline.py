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

import os
from rmake.lib.ninamori.compat import sha1


def _read_meta(path):
    if not os.path.isfile(path):
        return {}
    out = {}
    for line in open(path):
        key, value = line[:-1].split(' ', 1)
        out[key] = value
    return out


def _write_meta(path, meta):
    fobj = open(path, 'w')
    for key, value in sorted(meta.iteritems()):
        print >> fobj, key, value
    fobj.close()


class Timeline(object):
    def __init__(self, path):
        self.root = path
        self.meta = {}

    def _path(self, *names):
        return os.path.join(self.root, *names)

    def _snap(self, rev):
        return self._path('snapshots', rev)

    def _init(self):
        for subdir in ('master', 'snapshots', 'migrations'):
            path = self._path(subdir)
            if not os.path.isdir(path):
                os.makedirs(path)
        self.write_meta()

    def read_meta(self):
        self.meta = _read_meta(self._path('META'))

    def write_meta(self):
        _write_meta(self._path('META'), self.meta)

    def get(self, rev=None):
        self.read_meta()
        if rev is None:
            rev = self.meta['latest']
        if os.path.isfile(self._snap(rev) + '.txt'):
            return Revision(self, rev)
        else:
            return None

    def _list(self):
        out = []
        for name in os.listdir(self._path('snapshots')):
            if name.endswith('.txt'):
                out.append(name[:-4])
        return out

    def snapshot(self, rev_base):
        self._init()
        self.read_meta()

        master = self._path('master')
        contents = ''
        for name in sorted(os.listdir(master)):
            if not name.endswith('.sql'):
                continue
            contents += open(os.path.join(master, name)).read()

        # Check if the new revision would be identical to the previous one.
        # It's fine if it's identical to an older revision, though.
        digest = sha1(contents).hexdigest()
        if 'latest' in self.meta:
            latest = self.get()
            if latest.digest == digest:
                raise RuntimeError("New snapshot is identical to existing "
                        "latest snapshot %s" % (latest.rev,))

        # Revisions look like revbase-N-xxxxxx where N increments for each
        # unique revbase. Thus, we need to look at all the existing revisions
        # to find the highest N for the given revbase.
        idx = 0
        for existing in self._list():
            a, b, c = existing.rsplit('-', 2)
            if a != rev_base:
                continue
            idx = max(idx, int(b))
        idx += 1
        rev = '%s-%s-%s' % (rev_base, idx, digest[:6])
        base = self._snap(rev)

        # Write out the new revision and move the "latest" pointer.
        fobj = open(base + '.sql', 'w')
        fobj.write(contents)
        fobj.close()

        _write_meta(base + '.txt', {
            'digest': digest,
            })

        self.meta['latest'] = rev
        self.write_meta()

        return rev


class Revision(object):

    def __init__(self, timeline, rev):
        self.rev = rev
        self.base = timeline._snap(rev)
        self.meta = _read_meta(self.base + '.txt')

    digest = property(lambda self: self.meta['digest'])

    def read(self):
        return open(self.base + '.sql').read()

    def populate(self, cu):
        cu.execute(self.read())
