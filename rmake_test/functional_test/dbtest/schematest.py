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

import shutil

from conary import dbstore

from rmake_test import resources
from rmake_test import rmakehelp

from rmake.db import database
from rmake.db import schema


class SchemaTest(rmakehelp.RmakeHelper):

    def testMigrateAll(self):
        dbPath = self.workDir + '/jobs.db'
        shutil.copyfile(resources.get_archive('jobs.db.v1'))
        db = dbstore.connect(dbPath, driver = "sqlite", timeout=10000)
        db.loadSchema()
        cu = db.cursor()
        assert(cu.execute('select state from Jobs where jobId=1').next()[0] == -1)
        assert(cu.execute('select state from Jobs where jobId=3').next()[0] == 99)
        mgr = schema.SchemaManager(db)
        m = schema.Migrator(db, mgr)
        m.migrate(1, schema.SCHEMA_VERSION)
        db.loadSchema()
        assert(cu.execute('select state from Jobs where jobId=1').next()[0] == 1)
        assert(cu.execute('select state from Jobs where jobId=3').next()[0] == 5)
    def testMigrateDatabase(self):
        dbPath = self.workDir + '/jobs.db'
        shutil.copyfile(resources.get_archive('jobs.db.v5'))
        db = database.Database(('sqlite', dbPath), self.workDir + '/contents')

