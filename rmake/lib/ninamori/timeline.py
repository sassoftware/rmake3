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


import inspect
import logging
import os
from rmake.lib.ninamori import error
from rmake.lib.ninamori import graph
from rmake.lib.ninamori.compat import sha1
from rmake.lib.ninamori.decorators import protected

log = logging.getLogger(__name__)


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
    """
    Collection of snapshotted schema revisions and migration steps.
    """

    def __init__(self, path):
        self.root = path
        self.meta = {}

    def _path(self, *names):
        return os.path.join(self.root, *names)

    def _snap(self, rev):
        return self._path('snapshots', rev)

    def _migration(self, old_rev, new_rev):
        return self._path('migrations', '%s--%s' % (old_rev, new_rev))

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
        ctx = sha1()

        contents = ''
        for name in sorted(os.listdir(master)):
            if not name.endswith('.sql'):
                continue
            contents += open(os.path.join(master, name)).read()
        ctx.update(contents)

        code = None
        master_path = os.path.join(master, 'master.py')
        if os.path.exists(master_path):
            code = open(master_path, 'rU').read()
            tmp_globals = {}
            exec code in tmp_globals
            cls = tmp_globals.get('Script')
            if not inspect.isclass(cls) or not issubclass(cls, ScriptBase):
                raise RuntimeError("master.py must define a class 'Script' "
                        "that subclasses ninamori.timeline.ScriptBase")
            ctx.update(code)

        # Check if the new revision would be identical to the previous one.
        # It's fine if it's identical to an older revision, though.
        digest = ctx.hexdigest()
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
        noise = os.urandom(3).encode('hex')
        rev = '%s-%s-%s' % (rev_base, idx, noise)
        base = self._snap(rev)

        # Write out the new revision and move the "latest" pointer.
        meta = {
                'digest': digest,
                }

        fobj = open(base + '.sql', 'w')
        fobj.write(contents)
        fobj.close()

        if code:
            fobj = open(base + '.py', 'w')
            fobj.write(code)
            fobj.close()
            meta['has_code'] = 'True'

        _write_meta(base + '.txt', meta)

        self.meta['latest'] = rev
        self.write_meta()

        return rev

    def _migration_graph(self):
        g = graph.DirectedGraph()
        for edge in os.listdir(self._path('migrations')):
            if '--' not in edge or not edge.endswith('.txt'):
                continue
            one, two = edge[:-4].split('--')
            g.addEdge(one, two)
        return g

    def migrate(self, db, old_rev, new_rev):
        if old_rev == new_rev:
            return
        g = self._migration_graph()
        path = g.shortestPath(old_rev.rev, new_rev.rev)
        if path is None:
            raise error.MigrationError("No migration path between current "
                    "revision '%s' and desired revision '%s'" % (old_rev.rev,
                        new_rev.rev))
        log.debug("Migration path: %s", " -> ".join(path))

        old = path.pop(0)
        while path:
            new = path.pop(0)

            log.debug("Migrating from %s to %s", old, new)
            step = Migration(self, old, new)
            step.apply(db)

            old = new


class Step(object):
    """
    Base class for revision and migration objects.
    """

    def __init__(self, base):
        self.base = base
        self.meta = _read_meta(base + '.txt')

    def _read(self):
        sql = open(self.base + '.sql').read()

        if 'has_code' in self.meta:
            mod = {}
            execfile(self.base + '.py', mod)
            mig_class = mod['Script']
        else:
            mig_class = ScriptBase

        return sql, mig_class

    def apply(self, db):
        sql, mig_class = self._read()
        migration = mig_class(db, sql)
        migration.run()


class Revision(Step):
    """
    Info about a single revision snapshot.
    """

    def __init__(self, timeline, rev):
        Step.__init__(self, timeline._snap(rev))
        self.rev = rev

    digest = property(lambda self: self.meta['digest'])


class Migration(Step):
    """
    Info about a migration from one revision to another.
    """

    def __init__(self, timeline, old_rev, new_rev):
        Step.__init__(self, timeline._migration(old_rev, new_rev))
        self.old_rev = old_rev
        self.new_rev = new_rev


class ScriptBase(object):
    """
    Base class for snapshot and migration script overrides.

    This is used as-is for pure SQL steps, and subclassed by population and
    migration scripts.
    """

    def __init__(self, db, sql):
        self.db = db
        self.sql = sql

    @protected
    def run(self, cu):
        self.before()
        if self.sql:
            cu.execute(self.sql)
        self.after()

    def before(self):
        pass

    def after(self):
        pass
