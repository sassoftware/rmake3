#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
SQL schema for the persistent DB store for rmake
"""
from rmake import errors

# NOTE: this schema is sqlite-specific

SCHEMA_VERSION = 5

def createJobs(db):
    cu = db.cursor()
    commit = False
    if "Jobs" not in db.tables:
        cu.execute("""
        CREATE TABLE Jobs (
            jobId          INTEGER PRIMARY KEY AUTOINCREMENT,
            pid            INTEGER NOT NULL DEFAULT 0,
            uuid           CHAR(32) NOT NULL DEFAULT '',
            state          INTEGER NOT NULL DEFAULT 0,
            status         STRING NOT NULL DEFAULT 'JobID entry created',
            start          STRING NOT NULL DEFAULT '0',
            finish         STRING NOT NULL DEFAULT '0',
            failureReason  STRING NOT NULL DEFAULT '',
            failureData    STRING NOT NULL DEFAULT ''
        )""")
        db.tables["Jobs"] = []
        commit = True
    if commit:
        db.commit()
        db.loadSchema()

def createJobConfig(db):
    cu = db.cursor()
    commit = False
    if "JobConfig" not in db.tables:
        cu.execute("""
        CREATE TABLE JobConfig (
            jobId       INTEGER NOT NULL,
            key         STRING NOT NULL,
            ord         INTEGER NOT NULL,
            value       STRING NOT NULL
        )""")
        db.tables["JobConfig"] = []
        if db.createIndex("JobConfig", "JobConfigIdx", "jobId",
                          unique = False):
            commit = True
        if db.createIndex("JobConfig", "JobConfigKeyIdx", "jobId, key",
                          unique = False):
            commit = True
    if commit:
        db.commit()
        db.loadSchema()

def createSubscriber(db):
    cu = db.cursor()
    commit = False
    if "Subscriber" not in db.tables:
        cu.execute("""
         CREATE TABLE Subscriber(
             subscriberId  INTEGER PRIMARY KEY AUTOINCREMENT,
             jobId         INTEGER NOT NULL,
             uri           STRING  NOT NULL
         )""")
        db.tables["Subscriber"] = []
        commit = True

    if db.createIndex("Subscriber", "SubscriberJobIdx", "jobId"):
        commit = True

    if "SubscriberEvents" not in db.tables:
        cu.execute("""
        CREATE TABLE SubscriberEvents (
            subscriberId  INTEGER NOT NULL,
            event         STRING  NOT NULL,
            subevent      STRING  NOT NULL
        )""")
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
            subscriberId  STRING  NOT NULL,
            data          STRING  NOT NULL
        )""")
        db.tables["SubscriberData"] = []
        commit = True

    if db.createIndex("SubscriberData", "SubscriberDataIdx", "subscriberId"):
        commit = True

    if commit:
        db.commit()
        db.loadSchema()




def createBuildTroves(db):
    cu = db.cursor()
    commit = False
    if "BuildTroves" not in db.tables:
        # XXX: will normalize later
        cu.execute("""
        CREATE TABLE BuildTroves (
            troveId        INTEGER PRIMARY KEY AUTOINCREMENT,
            jobId          INTEGER NOT NULL,
            pid            INTEGER NOT NULL DEFAULT 0,
            troveName      STRING NOT NULL,
            version        STRING NOT NULL,
            flavor         STRING NOT NULL,
            state          INTEGER NOT NULL,
            status         STRING NOT NULL DEFAULT '',
            failureReason  STRING NOT NULL DEFAULT '',
            failureData    STRING NOT NULL DEFAULT '',
            start          STRING NOT NULL DEFAULT '0',
            finish         STRING NOT NULL DEFAULT '0',
            logPath        STRING NOT NULL DEFAULT '',
            recipeType     INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT BuildTroves_jobId_fk
                FOREIGN KEY(jobId) REFERENCES Jobs(jobId)
                ON DELETE CASCADE ON UPDATE RESTRICT
        )""")
        db.tables["BuildTroves"] = []
        commit = True
    if db.createIndex("BuildTroves", "BuildTrovesIdx",
                      "jobId, troveName, version, flavor", unique = True):
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

    if commit:
        db.commit()
        db.loadSchema()

def createBinaryTroves(db):
    cu = db.cursor()
    commit = False
    if "BinaryTroves" not in db.tables:
        cu.execute("""
        CREATE TABLE BinaryTroves (
            troveId     INTEGER NOT NULL,
            troveName   STRING,
            version     STRING,
            flavor      STRING,
            CONSTRAINT BinaryTroves_jobId_fk
                FOREIGN KEY(troveId) REFERENCES BuildTroves(troveId)
                ON DELETE CASCADE ON UPDATE RESTRICT
        )""")
        db.tables["BinaryTroves"] = []
        commit = True
    if db.createIndex("BinaryTroves", "BinaryTrovesIdx",
                      "troveId"):
        commit = True
    if commit:
        db.commit()
        db.loadSchema()

def createStateLogs(db):
    cu = db.cursor()
    commit = False
    if "StateLogs" not in db.tables:
        cu.execute("""
        CREATE TABLE StateLogs (
            logId    INTEGER PRIMARY KEY AUTOINCREMENT,
            jobId    INTEGER NOT NULL,
            troveId  INTEGER NOT NULL,
            message  STRING NOT NULL,
            args     STRING NOT NULL DEFAULT '',
            changed  STRING NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT StateLogsJob_fk
                FOREIGN KEY(jobId) REFERENCES Jobs(jobId)
                ON DELETE CASCADE ON UPDATE RESTRICT
        )""")
        db.tables["StateLogs"] = []
        commit = True
    if db.createIndex("StateLogs", "StateLogsJobTroveId", "jobId,troveId"):
        commit = True
    if commit:
        db.commit()
        db.loadSchema()


def createJobQueue(db):
    cu = db.cursor()
    commit = False
    if "JobQueue" not in db.tables:
        cu.execute("""
        CREATE TABLE JobQueue (
            jobId       INTEGER
        )""")
        db.tables["JobQueue"] = []
        commit = True
    if commit:
        db.commit()
        db.loadSchema()

def loadSchema(db):
    global SCHEMA_VERSION
    version = db.getVersion()

    if version == SCHEMA_VERSION:
        return version

    db.loadSchema()
    createJobs(db)
    createJobConfig(db)
    createBuildTroves(db)
    createBinaryTroves(db)
    createStateLogs(db)
    createSubscriber(db)
    createJobQueue(db)
    db.loadSchema()

    if version != SCHEMA_VERSION:
        return db.setVersion(SCHEMA_VERSION)

    return SCHEMA_VERSION

class Migrator(object):

    # FIXME: This migration code is susceptible to a sort of upgrade race
    # condition: if a table is created and migrated during the same run,
    # SQL that alters the table will fail. this only applies to rMake installs
    # that don't get upgraded very often. there are a few ways to accomodate
    # this, just be aware that nothing is yet implemented.

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

    def _addColumn(self, table, name, value):
        self.cu.execute('ALTER TABLE %s ADD COLUMN %s    %s' % (table, name, value))

    def migrate(self, currentVersion, newVersion):
        if currentVersion < newVersion:
            while currentVersion < newVersion:
                # migration returns the schema that they migrated to.
                currentVersion = getattr(self, 'migrateFrom' + str(currentVersion))()
        self.db.setVersion(newVersion)
        self.db.commit()

    def __init__(self, db):
        self.db = db
        self.cu = db.cursor()

def loadAndMigrate(db):
    schemaVersion = db.getVersion()
    if schemaVersion > SCHEMA_VERSION:
        raise errors.DatabaseSchemaTooNew()
    if not schemaVersion:
        loadSchema(db)
        return SCHEMA_VERSION
    else:
        db.loadSchema()
        if schemaVersion != SCHEMA_VERSION:
            Migrator(db).migrate(schemaVersion, SCHEMA_VERSION)
            db.loadSchema()
    return SCHEMA_VERSION
