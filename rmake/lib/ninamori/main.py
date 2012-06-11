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


import logging
import optparse
import os
import sys

from rmake.lib import ninamori
from rmake.lib.ninamori import timeline


def main():
    parser = optparse.OptionParser()
    parser.add_option('-d', '--schema-dir', default='.',
            help="Schema directory")
    parser.add_option('-v', '--verbose', action='store_true')
    options, args = parser.parse_args()
    if not args:
        parser.error("Expected a command: populate, migrate, snapshot")
    mode = args.pop(0)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    log = logging.getLogger()
    log.handlers = [handler]
    log.setLevel(options.verbose and logging.DEBUG or logging.INFO)

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
        db = ninamori.connect(dburl)
        db.attach(dtl, revision=rev, allowMigrate=True)

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
