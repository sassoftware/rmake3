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


import optparse
import os
import sys

from rmake.lib import ninamori
from rmake.lib.ninamori import timeline


def main():
    parser = optparse.OptionParser()
    parser.add_option('-d', '--schema-dir', default='.',
            help="Schema directory")
    options, args = parser.parse_args()
    if not args:
        parser.error("Expected a command: populate, migrate, snapshot")
    mode = args.pop(0)

    dtl = timeline.Timeline(os.path.realpath(options.schema_dir))
    dtl.read_meta()
    if mode == 'populate':
        if not (1 <= len(args) <= 2):
            sys.exit("Usage: populate <dburl> [<rev>]")
        dburl = args.pop(0)
        rev = args and args[0] or None
        db = ninamori.connect(dburl)
        db.attach(dtl, revision=rev, allowMigrate=False)

    elif mode == 'migrate':
        if not (1 <= len(args) <= 2):
            sys.exit("Usage: migrate <dburl> [<rev>]")
        dburl = args.pop(0)
        rev = args and args[0] or None
        timeline.connect(dburl)
        timeline.migrate(rev)
    elif mode == 'snapshot':
        if len(args) > 1:
            sys.exit("Usage: snapshot [<rev>]")
        elif args:
            rev = args[0]
        else:
            example = '1.0'
            if 'latest' in dtl.meta:
                latest = dtl.meta['latest']
                example = latest.rsplit('-', 2)[0]
                print 'Latest revision:', dtl.meta['latest']
            rev = raw_input("Next revision [%s] ? " % example)
            if not rev:
                rev = example
        rev = dtl.snapshot(rev)
        print "Created", rev
    else:
        parser.error("Expected a command: populate, migrate, snapshot")


if __name__ == '__main__':
    main()
