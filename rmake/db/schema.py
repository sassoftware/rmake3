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


"""
SQL schema for the persistent DB store for rmake
"""

from rmake import errors


SCHEMA_VERSION = 12

def createJobs(db):
    cu = db.cursor()
    commit = False
    if "Jobs" not in db.tables:
        cu.execute("""
        CREATE TABLE Jobs (
            jobId          %(PRIMARYKEY)s,
            pid            INTEGER NOT NULL DEFAULT 0,
            uuid           CHAR(32) NOT NULL DEFAULT '',
            state          INTEGER NOT NULL DEFAULT 0,
            status         TEXT NOT NULL DEFAULT 'JobID entry created',
            owner          TEXT NOT NULL DEFAULT '',
            start          TEXT NOT NULL DEFAULT '0',
            finish         TEXT NOT NULL DEFAULT '0',
            failureReason  smallint,
            failureData    %(BLOB)s
        )""" % db.keywords)
        db.tables["Jobs"] = []
        commit = True
    return commit

def createJobConfig(db):
    cu = db.cursor()
    commit = False
    if "JobConfig" not in db.tables:
        cu.execute("""
        CREATE TABLE JobConfig (
            jobId       INTEGER NOT NULL
                REFERENCES Jobs ON DELETE CASCADE,
            context     TEXT NOT NULL DEFAULT '',
            key         TEXT NOT NULL,
            ord         INTEGER NOT NULL,
            value       TEXT NOT NULL
        )""" % db.keywords)
        db.tables["JobConfig"] = []
    if db.createIndex("JobConfig", "JobConfigIdx", "jobId",
                      unique = False):
        commit = True
    if db.createIndex("JobConfig", "JobContextIdx", "jobId, context",
                      unique = False):
        commit = True
    if db.createIndex("JobConfig", "JobConfigContextKeyIdx", 
                      "jobId, context, key", unique = False):
        commit = True
    return commit

def createTroveSettings(db):
    cu = db.cursor()
    commit = False
    if "TroveSettings" not in db.tables:
        cu.execute("""
        CREATE TABLE TroveSettings (
            jobId      INTEGER NOT NULL
                REFERENCES Jobs ON DELETE CASCADE,
            troveId     INTEGER NOT NULL
                REFERENCES BuildTroves ON DELETE CASCADE,
            key         TEXT NOT NULL,
            ord         INTEGER NOT NULL,
            value       TEXT NOT NULL
        )""" % db.keywords)
        db.tables["TroveSettings"] = []
    if db.createIndex("TroveSettings", "TroveSettingsIdx", "jobId",
                      unique = False):
        commit = True
    if db.createIndex("TroveSettings", "TroveSettingsIdx2", "troveId",
                      unique = False):
        commit = True
    return commit


def createSubscriber(db):
    cu = db.cursor()
    commit = False
    if "Subscriber" not in db.tables:
        cu.execute("""
         CREATE TABLE Subscriber(
             subscriberId  %(PRIMARYKEY)s,
             jobId         INTEGER,
             uri           TEXT  NOT NULL
         )""" % db.keywords)
        db.tables["Subscriber"] = []
        commit = True

    if db.createIndex("Subscriber", "SubscriberJobIdx", "jobId"):
        commit = True

    if "SubscriberEvents" not in db.tables:
        cu.execute("""
        CREATE TABLE SubscriberEvents (
            subscriberId  INTEGER NOT NULL,
            event         TEXT  NOT NULL,
            subevent      TEXT  NOT NULL
        )""" % db.keywords)
        db.tables["SubscriberEvents"] = []
        commit = True


    if db.createIndex("SubscriberEvents", "SubscriberEventsIdx",
                      "subscriberId"):
        commit = True


    if db.createIndex("SubscriberEvents", "SubscriberEventsEventIdx",
                      "event,subevent"):
        commit = True

    if "SubscriberData" not in db.tables:
        cu.execute("""
        CREATE TABLE SubscriberData (
            subscriberId  integer  NOT NULL,
            data          TEXT  NOT NULL
        )""" % db.keywords)
        db.tables["SubscriberData"] = []
        commit = True

    if db.createIndex("SubscriberData", "SubscriberDataIdx", "subscriberId"):
        commit = True

    return commit


def createBuildTroves(db):
    cu = db.cursor()
    commit = False
    if "BuildTroves" not in db.tables:
        # XXX: will normalize later
        cu.execute("""
        CREATE TABLE BuildTroves (
            troveId        %(PRIMARYKEY)s,
            jobId          INTEGER NOT NULL
                REFERENCES Jobs ON DELETE CASCADE,
            pid            INTEGER NOT NULL DEFAULT 0,
            troveName      TEXT NOT NULL,
            troveType      TEXT NOT NULL DEFAULT 'build',
            version        TEXT NOT NULL,
            flavor         TEXT NOT NULL,
            context        TEXT NOT NULL DEFAULT '',
            state          INTEGER NOT NULL,
            status         TEXT NOT NULL DEFAULT '',
            failureReason  smallint,
            failureData    %(BLOB)s,
            start          TEXT NOT NULL DEFAULT '0',
            finish         TEXT NOT NULL DEFAULT '0',
            logPath        TEXT NOT NULL DEFAULT '',
            recipeType     INTEGER NOT NULL DEFAULT 1,
            chrootId       INTEGER NOT NULL DEFAULT 0,
            buildType      INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT BuildTroves_jobId_fk
                FOREIGN KEY(jobId) REFERENCES Jobs(jobId)
                ON DELETE CASCADE ON UPDATE RESTRICT
        )""" % db.keywords)
        db.tables["BuildTroves"] = []
        commit = True
    if db.createIndex("BuildTroves", "BuildTrovesIdx",
                      "jobId, troveName, version, flavor",
                      unique = False):
        commit = True
    if db.createIndex("BuildTroves", "BuildTrovesContextIdx",
                      "jobId, troveName, version, flavor, context",
                      unique = True):
        commit = True
    if db.createIndex("BuildTroves", "BuildTroveJobIdIdx", "jobId",
                      unique = False):
        commit = True

    if db.createIndex("BuildTroves", "BuildTroveIdIdx", "troveId",
                      unique = False):
        commit = True
    if db.createIndex("BuildTroves", "BuildTrovesStateIdx", "jobId, state",
                      unique = False):
        commit = True

    return commit

def createBinaryTroves(db):
    cu = db.cursor()
    commit = False
    if "BinaryTroves" not in db.tables:
        cu.execute("""
        CREATE TABLE BinaryTroves (
            troveId     INTEGER NOT NULL,
            troveName   TEXT,
            version     TEXT,
            flavor      TEXT,
            CONSTRAINT BinaryTroves_jobId_fk
                FOREIGN KEY(troveId) REFERENCES BuildTroves(troveId)
                ON DELETE CASCADE ON UPDATE RESTRICT
        )""" % db.keywords)
        db.tables["BinaryTroves"] = []
        commit = True
    if db.createIndex("BinaryTroves", "BinaryTrovesIdx",
                      "troveId"):
        commit = True
    return commit

def createStateLogs(db):
    cu = db.cursor()
    commit = False
    if "StateLogs" not in db.tables:
        # NB: troveId NULL means logs are for a job
        cu.execute("""
        CREATE TABLE StateLogs (
            logId    %(PRIMARYKEY)s,
            jobId    INTEGER NOT NULL
                REFERENCES Jobs ON DELETE CASCADE,
            troveId  INTEGER
                REFERENCES BuildTroves ON DELETE CASCADE,
            message  TEXT NOT NULL,
            args     TEXT NOT NULL DEFAULT '',
            changed  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""" % db.keywords)
        db.tables["StateLogs"] = []
        commit = True
    if db.createIndex("StateLogs", "StateLogsJobTroveId", "jobId,troveId"):
        commit = True

    return commit


def createJobQueue(db):
    cu = db.cursor()
    commit = False
    if "JobQueue" not in db.tables:
        cu.execute("""
        CREATE TABLE JobQueue (
            jobId       INTEGER
                REFERENCES Jobs ON DELETE CASCADE
        )""" % db.keywords)
        db.tables["JobQueue"] = []
        commit = True

    return commit

def createChroots(db):
    cu = db.cursor()
    commit = False
    if "Chroots" not in db.tables:
        cu.execute("""
        CREATE TABLE Chroots (
            chrootId      %(PRIMARYKEY)s,
            nodeName      TEXT,
            path          TEXT,
            troveId       INTEGER
                REFERENCES BuildTroves ON DELETE SET NULL,
            active        INTEGER NOT NULL
        )""" % db.keywords)
        db.tables["Chroots"] = []
        commit = True
    if db.createIndex("Chroots", "ChrootdsIdx", "troveId"):
        commit = True

    return commit

def createNodes(db):
    cu = db.cursor()
    commit = False
    if "Nodes" not in db.tables:
        cu.execute("""
        CREATE TABLE Nodes (
            nodeName     TEXT PRIMARY KEY NOT NULL,
            host         TEXT NOT NULL,
            slots        INTEGER NOT NULL,
            buildFlavors TEXT NOT NULL,
            active       INTEGER NOT NULL DEFAULT 0
        )""" % db.keywords)
        db.tables["Nodes"] = []
        commit = True
    return commit

def createAuthCache(db):
    cu = db.cursor()
    commit = False
    if "AuthCache" not in db.tables:
        cu.execute("""
        CREATE TABLE AuthCache (
            sessionId    %(BINARY20)s PRIMARY KEY NOT NULL,
            timeStamp    FLOAT NOT NULL
        )""" % db.keywords)
        db.tables["AuthCache"] = []
        commit = True

    return commit

def createPluginVersionTable(db):
    cu = db.cursor()
    commit = False
    if "PluginVersion" not in db.tables:
        cu.execute("""
        CREATE TABLE PluginVersion (
            plugin      TEXT NOT NULL UNIQUE,
            version     INTEGER
        )""" % db.keywords)
        db.tables["PluginVersion"] = []
        commit = True

    return commit

class AbstractSchemaManager(object):
    def __init__(self, db):
        self.db = db
        self.currentVersion = self.getLatestVersion()


    def loadSchema(self):
        db = self.db
        version = self.getVersion()

        if version == self.currentVersion:
            return version

        db.loadSchema()
        self.createTables()
        db.loadSchema()

        if version != self.currentVersion:
            return self.setVersion(self.currentVersion)

        return self.currentVersion

    def getVersion(self):
        return self.db.getVersion()

    def setVersion(self, version):
        self.db.setVersion(version)

    def loadAndMigrate(self):
        schemaVersion = self.getVersion()
        if schemaVersion > self.currentVersion:
            raise errors.DatabaseSchemaTooNew()
        if not schemaVersion:
            self.loadSchema()
            return self.currentVersion
        else:
            self.db.loadSchema()
            if schemaVersion != self.currentVersion:
                self.migrate(schemaVersion, self.currentVersion)
                self.loadSchema()
        return self.currentVersion

class AbstractMigrator(object):

    # FIXME: This migration code is susceptible to a sort of upgrade race
    # condition: if a table is created and migrated during the same run,
    # SQL that alters the table will fail. this only applies to rMake installs
    # that don't get upgraded very often. there are a few ways to accomodate
    # this, just be aware that nothing is yet implemented.

    def _addColumn(self, table, name, value):
        self.cu.execute('ALTER TABLE %s ADD COLUMN %s    %s' % (table, name,
                                                                value))

    def _rebuildTable(self, table):
        tmpTable = table + '_tmp'
        cu = self.db.cursor()

        # Drop old indexes because index names must be globally unique.
        for index in list(self.db.tables[table]):
            self.db.dropIndex(table, index)

        # Rename old -> tmp
        cu.execute("ALTER TABLE %s RENAME TO %s" % (table, tmpTable))
        del self.db.tables[table]

        # Recreate schema
        assert self.schemaMgr.createTables(doCommit=False)

        # Figure out which columns to copy
        cu.execute("SELECT * FROM %s LIMIT 1" % tmpTable)
        inFields = set(x.lower() for x in cu.fields())
        cu.execute("SELECT * FROM %s LIMIT 1" % table)
        outFields = set(x.lower() for x in cu.fields())
        assert inFields == outFields

        # Copy
        fieldNames = ', '.join(inFields)
        cu.execute("INSERT INTO %s ( %s ) SELECT %s FROM %s" % (table,
            fieldNames, fieldNames, tmpTable))
        cu.execute("DROP TABLE %s" % tmpTable)

    def migrate(self, currentVersion, newVersion):
        self.db.transaction()
        if currentVersion < newVersion:
            while currentVersion < newVersion:
                # migration returns the schema that they migrated to.
                currentVersion = getattr(self, 'migrateFrom' + str(currentVersion))()
        self.schemaMgr.setVersion(newVersion)
        self.db.commit()

    def __init__(self, db, schemaMgr):
        self.db = db
        self.cu = db.cursor()
        self.schemaMgr = schemaMgr

class SchemaManager(AbstractSchemaManager):

    def createTables(self, doCommit=True):
        db = self.db
        if doCommit:
            db.transaction()

        changed = False
        changed |= createJobs(db)
        changed |= createJobConfig(db)
        changed |= createBuildTroves(db)
        changed |= createTroveSettings(db)
        changed |= createBinaryTroves(db)
        changed |= createStateLogs(db)
        changed |= createSubscriber(db)
        changed |= createJobQueue(db)
        changed |= createChroots(db)
        changed |= createNodes(db)
        changed |= createPluginVersionTable(db)
        changed |= createAuthCache(db)

        if changed and doCommit:
            db.commit()
        db.loadSchema()
        return changed

    def migrate(self, oldVersion, newVersion):
        Migrator(self.db, self).migrate(oldVersion, newVersion)

    def getLatestVersion(self):
        return SCHEMA_VERSION

class Migrator(AbstractMigrator):
    def migrateFrom1(self):
        self._addColumn('Jobs', "uuid", "CHAR(32) NOT NULL DEFAULT ''")

        return 2

    def migrateFrom2(self):
        self._addColumn('Jobs', "pid", "INTEGER NOT NULL DEFAULT 0")
        self._addColumn('BuildTroves', "pid", "INTEGER NOT NULL DEFAULT 0")
        return 3

    def migrateFrom3(self):
        self.cu.execute("UPDATE Jobs SET state = state + 1000")
        for iState, fState in [(999, 1), (1000, 0), (1001, 2), (1002, 3),
                               (1003, 4), (1099, 5), (1100, 6), (1101, 7)]:
            self.cu.execute("UPDATE Jobs SET state=? WHERE state=?",
                            fState, iState)
        return 4

    def migrateFrom4(self):
        self._addColumn('BuildTroves', "recipeType",
                        "INTEGER NOT NULL DEFAULT 0")
        return 5

    def migrateFrom5(self):
        self._addColumn('BuildTroves', "chrootId",
                        "INTEGER NOT NULL DEFAULT 0")
        createChroots(self.db)
        createNodes(self.db)
        createPluginVersionTable(self.db)
        return 6

    def migrateFrom6(self):
        self._addColumn('BuildTroves', "context",
                        "TEXT NOT NULL DEFAULT ''")
        self._addColumn('JobConfig',  "context",
                        "TEXT NOT NULL DEFAULT ''")
        self._addColumn('BuildTroves', "buildType",
                        "INTEGER NOT NULL DEFAULT 0")
        self.cu.execute("DROP INDEX BuildTrovesIdx") # this idx is no longer
                                                     # unique
        createJobConfig(self.db) # add index
        createBuildTroves(self.db) # add indexes
        return 8

    def migrateFrom7(self):
        self._addColumn('BuildTroves', "buildType",
                        "INTEGER NOT NULL DEFAULT 0")
        return 8

    def migrateFrom8(self):
        createAuthCache(self.db)
        return 9

    def migrateFrom9(self):
        self._addColumn("Jobs", "owner",
                        "TEXT NOT NULL DEFAULT ''")
        return 10

    def migrateFrom10(self):
        sql, = self.db.cursor().execute('select sql from sqlite_master'
                                        ' where tbl_name="BuildTroves"').next()
        if 'troveType' in sql:
            return 11
        createTroveSettings(self.db)
        self._addColumn("BuildTroves", "troveType",
                        "troveType      TEXT NOT NULL DEFAULT 'build'")
        return 11

    def migrateFrom11(self):
        if self.db.driver == 'sqlite':
            cu = self.db.cursor()
            for table in ['Jobs', 'Subscriber', 'SubscriberData', 'BuildTroves',
                    'StateLogs', 'Chroots', 'AuthCache']:
                self._rebuildTable(table)
            cu.execute("""UPDATE Jobs SET failureReason = NULL,
                    failureData = NULL WHERE failureReason = ''""")
            cu.execute("""UPDATE BuildTroves SET failureReason = NULL,
                    failureData = NULL WHERE failureReason = ''""")
            cu.execute("UPDATE StateLogs SET troveId = NULL WHERE troveId = 0")
        return 12

class PluginSchemaManager(AbstractSchemaManager):
    """
        Not used at the moment but here's a way to add plugin-specific tables
        to rMake.
    """

    def getVersion(self):
        cu = self.db.cursor()
        rv = cu.execute('SELECT version from PluginVersion WHERE plugin=?', 
                        self.name).fetchall()
        if rv:
            return rv[0][0]
        else:
            return None

    def getLatestVersion(self):
        return SCHEMA_VERSION

    def setVersion(self, version):
        if self.getVersion() is None:
            cu = self.db.cursor()
            rv = cu.execute('INSERT INTO PluginVersion VALUES (?, ?)', 
                            self.name, version)
        else:
            cu = self.db.cursor()
            rv = cu.execute('UPDATE PluginVersion SET version=? WHERE'
                            'plugin=?', version, self.name)
