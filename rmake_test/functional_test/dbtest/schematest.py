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
