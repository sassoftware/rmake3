#
# Copyright (c) 2006-2010 rPath, Inc.
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

"""
This module holds the database interface used by the trove build system, as an
extension of the core build system.
"""

import cPickle
import os
from conary.deps import deps
from conary import versions
from conary.deps.deps import ThawFlavor
from conary.versions import ThawVersion
from rmake.build import buildjob
from rmake.build import buildtrove
from rmake.errors import JobNotFound
from rmake.lib.ninamori.decorators import protected, readOnly


class JobStore(object):

    def __init__(self, db):
        self.db = db

    @protected
    def createJob(self, cu, job):
        """Add build-specific data to the appropriate table after creating the
        core job object.

        This also assigns the job its jobId.

        NB: builds.jobs only holds things that need to be indexed and searched
        on without unpickling the job blob in the core jobs table.
        """
        cu.insert('build.jobs',
                dict(job_uuid=job.jobUUID, job_name=job.jobName),
                returning='job_id')
        job.jobId = cu.fetchone()[0]

        for trove in job.iterTroves():
            cu.insert('build.job_troves', dict(
                job_uuid=job.jobUUID,
                source_name=trove.name,
                source_version=trove.version.freeze(),
                build_flavor=trove.flavor.freeze(),
                build_context=trove.context,
                trove_state=trove.state,
                trove_status=trove.status,
                ))

        return job.jobId


class UNPORTED_JobStore(object):

    def UNPORTED_isJobBuilding(self):
        cu = self.db.cursor()
        cu.execute("SELECT COUNT(*) FROM Jobs WHERE state in (?, ?)", 
                   JOB_STATE_BUILD, JOB_STATE_STARTED)
        return cu.fetchone()[0]

    def UNPORTED_jobExists(self, jobId):
        cu = self.db.cursor()
        cu.execute("SELECT COUNT(*) FROM Jobs WHERE jobId=?", jobId)
        ret = cu.fetchone()[0]
        return ret

    def UNPORTED_listJobs(self, activeOnly=False, jobLimit=None):
        cu = self.db.cursor()
        sql = """SELECT jobId FROM Jobs"""
        if activeOnly:
            sql += ' WHERE state in (%s)' % ','.join(str(x) for x in buildjob.ACTIVE_STATES)
        sql += ' ORDER BY jobId DESC'
        if jobLimit:
            sql += ' LIMIT %d' % jobLimit
        return list(reversed([x[0] for x in cu.execute(sql)]))

    def UNPORTED_listTrovesByState(self, jobId, state=None):
        cu = self.db.cursor()
        cmd = """SELECT troveName, version, flavor, context, state 
                 FROM BuildTroves 
                 WHERE jobId=?"""
        params = [jobId]
        if state is not None:
            cmd += ' AND state=?'
            params.append(state)
        results = {}
        for (name, version, flavor, context, state) in cu.execute(cmd, params):
            version, flavor = thaw('version', version), thaw('flavor', flavor)
            if state in results:
                results[state].append((name, version, flavor, context))
            else:
                results[state] = [(name, version, flavor, context)]
        return results

    def UNPORTED_getJob(self, job_uuid, withTroves=False, withConfigs=True):
        return self.getJobs([job_uuid], withTroves=withTroves,
                withConfigs=withConfigs)[0]

    @readOnly
    def UNPORTED_getJobs(self, cu, job_uuids, withTroves=False, withConfigs=False):
        cu.execute("CREATE TEMPORARY TABLE t_jobs ( uuid TEXT )")
        cu.executemany("INSERT INTO t_jobs VALUES ( %s )",
                [(x,) for x in job_uuids])

        cu.execute("""
            SELECT t_jobs.uuid, job_uuid, job_id, job_name, state, status,
                owner, failure,
                EXTRACT(EPOCH FROM time_started) AS time_started,
                EXTRACT(EPOCH FROM time_updated) AS time_updated,
                EXTRACT(EPOCH FROM time_finished) AS time_finished
            FROM t_jobs LEFT JOIN jobs ON t_jobs.uuid = jobs.job_uuid
            """)

        jobs = {}
        for row in cu:
            job_uuid = row['job_uuid']
            if job_uuid is None:
                # Job not found.
                raise JobNotFound(row['uuid'])

            failure = row['failure']
            if failure is not None:
                failure = cPickle.loads(failure)

            jobs[job_uuid] = buildjob.BuildJob(
                    jobUUID=job_uuid,
                    jobId=row['job_id'],
                    jobName=row['job_name'],
                    state=row['state'],
                    status=row['status'],
                    timeStarted=row['time_started'],
                    timeUpdated=row['time_updated'],
                    timeFinished=row['time_finished'],
                    failure=failure)

        if False: #if withTroves:
            if False:
                results = cu.execute(
                """
                    SELECT jobId, BuildTroves.troveId, troveName, version,
                        flavor, context, state, status, failureReason, 
                        failureData, start, finish, logPath, pid, recipeType,
                        buildType, troveType, Chroots.path, Chroots.nodeName
                        FROM tJobIdList
                        JOIN BuildTroves USING(jobId)
                        LEFT JOIN Chroots USING(chrootId)
                """)

                trovesById = {}

                for (jobId, troveId, name, version, flavor, context,
                     state, status, failureReason, failureData, start, finish,
                     logPath, pid, recipeType, buildType, troveType,
                     chrootPath, chrootHost) in results:

                    if chrootPath is None:
                        chrootPath = ''
                        chrootHost = ''
                    version = versions.ThawVersion(version)
                    flavor = ThawFlavor(flavor)
                    failureReason = thaw('FailureReason',
                                         (failureReason, failureData))
                    troveClass = buildtrove.getClassForTroveType(troveType)
                    buildTrove = troveClass(jobId, name, version, 
                                            flavor,
                                            state=state, start=float(start),
                                            finish=float(finish),
                                            logPath=logPath, status=status,
                                            failureReason=failureReason,
                                            pid=pid, recipeType=recipeType,
                                            chrootPath=chrootPath,
                                            chrootHost=chrootHost,
                                            buildType=buildType,
                                            context=context)
                    trovesById[troveId] = buildTrove
                    jobsById[jobId].addTrove(name, version, flavor, context,
                                             buildTrove)

                results = cu.execute("""SELECT troveId, BinaryTroves.troveName, 
                                                BinaryTroves.version,
                                                BinaryTroves.flavor
                                                FROM tJobIdList
                                                JOIN BuildTroves USING(jobId)
                                                JOIN BinaryTroves USING(troveId)
                                     """)
                builtTroves = {}
                for troveId, name, version, flavor in results:
                    builtTroves.setdefault(troveId, []).append((
                            name, ThawVersion(version), ThawFlavor(flavor)))
                for troveId, binTroves in builtTroves.iteritems():
                    trovesById[troveId].setBuiltTroves(binTroves)

                cu.execute("""SELECT troveId, key, value
                              FROM tJobIdList
                              JOIN TroveSettings USING(jobId)
                              ORDER by key, ord""")
                troveSettings = {}
                for troveId, key, value in cu:
                    d = troveSettings.setdefault(troveId, {})
                    d.setdefault(key, []).append(value)
                for troveId, settings in troveSettings.items():
                    settingsClass = settings.pop('_class')[0]
                    trovesById[troveId].settings = thaw('TroveSettings',
                                                    (settingsClass, settings))
            else:
                results = cu.execute('''
                SELECT BuildTroves.jobId, troveName, version, flavor, context
                    FROM tJobIdList
                    JOIN BuildTroves USING(jobId)
                ''')
                for (jobId, n,v,f, context) in results:
                    jobsById[jobId].addTrove(n, versions.ThawVersion(v),
                                             ThawFlavor(f), context)
            if withConfigs:
                cu.execute("""SELECT jobId, context, key, value
                              FROM tJobIdList
                              JOIN JobConfig USING(jobId) 
                              ORDER by key, ord""")
                jobConfigD = {}
                for jobId, context, key, value in cu:
                    configD = jobConfigD.setdefault(jobId, {})
                    d = configD.setdefault(context, {})
                    d.setdefault(key, []).append(value)
                for jobId, configD in jobConfigD.items():
                    configD = dict((x[0], thaw('BuildConfiguration', x[1]))
                                   for x in configD.iteritems())
                    jobsById[jobId].setConfigs(configD)

        return [jobs[x] for x in job_uuids]

    def UNPORTED_getConfig(self, jobId, context):
        cu = self.db.cursor()
        cu.execute("""SELECT  key, value
                      FROM JobConfig WHERE jobId=? AND context=?
                      ORDER by key, ord""", jobId, context)
        frozenCfg = {}
        for key, value in cu:
            frozenCfg.setdefault(key, []).append(value)
        cfg = thaw('BuildConfiguration', frozenCfg)
        return cfg

    def UNPORTED__getTroveId(self, cu, jobId, name, version, flavor, context=''):
        cu.execute(
            '''
            SELECT troveId
                FROM BuildTroves
                WHERE jobId=? AND troveName=? AND version=?  AND flavor=? AND context=?
            ''',
            jobId, name, version.freeze(), flavor.freeze(), context)

        return self.db._getOne(cu, (jobId, name, version, flavor, context))[0]

    def UNPORTED_getJobsByState(self, state, withTroves=False):
        cu = self.db.cursor()
        jobIds = cu.execute('SELECT jobId FROM Jobs WHERE state=?',
                            state).fetchall()
        return self.getJobs([x[0] for x in jobIds], withTroves=withTroves)

    def UNPORTED_getJobIdsFromUUIDs(self, uuids):
        cu = self.db.cursor()
        # would a temporary table be more efficient?  I'm not sure
        jobIds = []
        for uuid in uuids:
            cu.execute('''SELECT jobId FROM Jobs where uuid=?''', uuid)
            jobIds.append(self.db._getOne(cu, uuid)[0])
        return jobIds

    def UNPORTED_getTrove(self, jobId, name, version, flavor, context=''):
        return self.getTroves([(jobId, name, version, flavor, context)])[0]

    def UNPORTED_getTroves(self, troveList):
        cu = self.db.cursor()
        cu.execute('''CREATE TEMPORARY TABLE tTroveInfo(
                          jobId integer,
                          troveName text,
                          version text,
                          flavor text,
                          context text
                      )''', start_transaction=False)
        try:

            for jobId, troveName, version, flavor, context in troveList:
                cu.execute('''INSERT INTO tTroveInfo VALUES (?, ?, ?, ?, ?)''',
                           (jobId, troveName, version.freeze(), flavor.freeze(),
                           context), start_transaction=False)

            results = cu.execute(
            """
                SELECT BuildTroves.troveId, jobId, pid, troveName, version,
                    flavor, context, state, status, failureReason, failureData,
                    start, finish, logPath, recipeType,
                    Chroots.nodeName, Chroots.path, troveType
                    FROM tTroveInfo
                    JOIN BuildTroves USING(jobId, troveName, version, flavor, context)
                    LEFT JOIN Chroots USING(chrootId)
            """)

            trovesById = {}
            trovesByNVF = {}
            # FIXME From here on out it's mostly duplication from getJobs code
            for (troveId, jobId, pid, troveName, version, flavor, context, state, 
                 status, failureReason, failureData, start, finish, logPath, 
                 recipeType, chrootHost, chrootPath, troveType) \
                 in results:
                if chrootPath is None:
                    chrootPath = chrootHost = ''
                version = versions.ThawVersion(version)
                flavor = ThawFlavor(flavor)
                failureReason = thaw('FailureReason',
                                     (failureReason, failureData))

                troveClass = buildtrove.getClassForTroveType(troveType)
                buildTrove = troveClass(jobId, troveName, version,
                                        flavor, context=context, pid=pid,
                                        state=state, start=float(start),
                                        finish=float(finish),
                                        logPath=logPath, status=status,
                                        failureReason=failureReason,
                                        recipeType=recipeType,
                                        chrootPath=chrootPath,
                                        chrootHost=chrootHost)
                trovesById[troveId] = buildTrove
                trovesByNVF[(jobId, troveName, version, 
                             flavor, context)] = buildTrove

            results = cu.execute(
            """
                SELECT troveId, BinaryTroves.troveName, BinaryTroves.version, 
                       BinaryTroves.flavor
                    FROM tTroveInfo
                    JOIN BuildTroves USING(jobId, troveName, version, flavor, context)
                    JOIN BinaryTroves USING(troveId)
            """)

            builtTroves = {}
            for troveId, troveName, version, flavor in results:
                builtTroves.setdefault(troveId, []).append((
                        troveName, ThawVersion(version), ThawFlavor(flavor)))
            for troveId, binTroves in builtTroves.iteritems():
                trovesById[troveId].setBuiltTroves(binTroves)

            cu.execute("""SELECT troveId, key, value
                          FROM tTroveInfo
                          JOIN BuildTroves USING(jobId, troveName, version, flavor,context)
                          JOIN TroveSettings USING(troveId)
                          ORDER by key, ord""")
            troveSettings = {}
            for troveId, key, value in cu:
                d = troveSettings.setdefault(troveId, {})
                d.setdefault(key, []).append(value)
            for troveId, settings in troveSettings.items():
                settingsClass = settings.pop('_class')[0]
                trovesById[troveId].settings = thaw('TroveSettings',
                                                (settingsClass, settings))

            out = []
            for tup in troveList:
                if tup in trovesByNVF:
                    out.append(trovesByNVF[tup])
                else:
                    raise KeyError(tup)
            return out
        finally:
            cu.execute("DROP TABLE tTroveInfo", start_transaction = False)



    # return all the log messages since last mark
    def UNPORTED_getJobLogs(self, jobId, mark = 0):
        cu = self.db.cursor()
        ret = []
        cu.execute("""
        SELECT changed, message, args FROM StateLogs
        WHERE jobId = ? AND troveId IS NULL ORDER BY logId LIMIT ? OFFSET ?
        """, (jobId, 100, mark))
        return cu.fetchall()

    # return all the log messages since last mark
    def UNPORTED_getTroveLogs(self, jobId, troveTuple, mark = 0):
        if len(troveTuple) == 3:
            (name, version, flavor) = troveTuple
            context = ''
        else:
            (name, version, flavor, context) = troveTuple
        cu = self.db.cursor()
        troveId = self._getTroveId(cu, jobId, name, version, flavor, context)
        ret = []
        cu.execute("""
        SELECT changed, message, args FROM StateLogs
        WHERE jobId = ? AND troveId=? ORDER BY logId LIMIT ? OFFSET ?
        """, (jobId, troveId, 100, mark))
        return cu.fetchall()

    def UNPORTED_getJobConfig(self, jobId):
        cu = self.db.cursor()
        d = {}
        cu.execute("""SELECT key, value FROM JobConfig
                       WHERE jobId=? AND context='' ORDER by key, ord""", jobId)
        for key, value in cu:
            d.setdefault(key, []).append(value)
        return thaw('BuildConfiguration', d)

    #----------------------------------------------------------------
    # 
    #  Modification - JobStore modification below this line.
    #
    #---------------------------------------------------------------

    @protected
    def UNPORTED_addJob(self, cu, job):
        job.jobUUID = os.urandom(16).encode('hex')
        job.state = JOB_STATE_INIT
        job.status = buildjob.stateNames[job.state]
        job.owner = '<unknown>'

        config = cPickle.dumps(job.config[''], 2)
        cu.execute("""
            INSERT INTO Jobs (job_uuid, job_name, state, status, owner, config)
            VALUES (%s, %s, %s, %s, %s)
            """, (job.jobUUID, job.jobName, job.state, job.status, job.owner))
        job.jobId = cu.lastrowid

        for trove in job.iterTroves():
            trove.jobUUID = job.jobUUID
            trove.state = TROVE_STATE_INIT
            trove.status = buildtrove.stateNames[trove.state]

            (troveName, version,
                flavor, context) = trove.getNameVersionFlavor(True)
            settings = cPickle.dumps(trove.settings, 2)
            config = cPickle.dumps(job.configs[context], 2)
            cu.execute("""
                INSERT INTO BuildTroves (job_uuid, trove_name, trove_version,
                    trove_flavor, context, state, status, build_type,
                    trove_type, settings, config)
                VALUES ( %s, %s, %s, %s, %s, %s, %s, %s)
                """, (job.jobUUID, troveName, version.freeze(), flavor.freeze(),
                    context, trove.state, trove.status, trove.buildType,
                    trove.troveType, settings, config))

        return job.jobUUID

    def UNPORTED_deleteJobs(self, jobIdList):
        cu = self.db.cursor()
        troveIdList = []
        troveList = []
        for jobId in jobIdList:
            cu.execute('''SELECT troveId, troveName, version, flavor 
                                      FROM BuildTroves WHERE jobId=?''', jobId)
            for troveId, name, version, flavor in cu:
                version = versions.ThawVersion(version)
                flavor = deps.ThawFlavor(flavor)
                troveList.append((jobId, name, version, flavor))
                cu.execute('DELETE FROM BinaryTroves where troveId=?', troveId)

            for table in ['Jobs', 'JobConfig', 'Subscriber', 'BuildTroves',
                          'StateLogs', 'JobQueue' ]:
                cu.execute('DELETE FROM %s WHERE jobId=?' % table, jobId)
            cu.execute('''DELETE FROM JobConfig
                          WHERE key="jobContext" AND value=?''', jobId)
        return troveList

    def UNPORTED_addJobConfig(self, jobId, context, jobConfig):
        cu = self.db.cursor()
        cu.execute('DELETE FROM JobConfig where jobId=? and context=?', jobId,
                    context)
        d = freeze('BuildConfiguration', jobConfig)
        for key, values in d.iteritems():
            for idx, value in enumerate(values):
                cu.execute('''INSERT INTO JobConfig 
                              (jobId, context, key, ord, value)
                              VALUES (?, ?, ?, ?, ?)''', jobId, context, key,
                                                      idx, value)

    def UNPORTED_setBinaryTroves(self, buildTrove, troveList):
        cu = self.db.cursor()
        troveId = self._getTroveId(cu, buildTrove.jobId,
                                   *buildTrove.getNameVersionFlavor(True))

        cu.execute('DELETE FROM BinaryTroves WHERE troveId=?', troveId)
        for binName, binVersion, binFlavor in troveList:
            cu.execute("INSERT INTO BinaryTroves "
                       "(troveId, troveName, version, flavor) "
                       "VALUES (?, ?, ?, ?)", (
                            troveId, binName,
                            binVersion.freeze(), binFlavor.freeze()))

    def UNPORTED_updateJob(self, job):
        cu = self.db.cursor()
        failureTup = freeze('FailureReason', job.getFailureReason())
        if failureTup[0] == '':
            failureTup = None, None
        cu.execute("""UPDATE Jobs set pid = ?, state = ?, status = ?, 
                                      start = ?, finish = ?, failureReason = ?, 
                                      failureData = ?
                       WHERE jobId = ?""",
                   (job.pid, job.state, job.status, job.start, job.finish, 
                    failureTup[0], failureTup[1], job.jobId))

    def UNPORTED_updateTrove(self, trove):
        cu = self.db.cursor()

        if trove.getChrootHost():
            chrootId = self.db._getChrootIdForTrove(trove)
        else:
            chrootId = 0

        failureTup = freeze('FailureReason', trove.getFailureReason())
        if failureTup[0] == '':
            failureTup = None, None
        kw = dict(pid=trove.pid, 
                  start=trove.start,
                  finish=trove.finish,
                  logPath=trove.logPath,
                  status=trove.status,
                  state=trove.state,
                  failureReason=failureTup[0],
                  failureData=failureTup[1],
                  recipeType=trove.recipeType,
                  buildType=trove.buildType,
                  chrootId=chrootId)
        fieldList = '=?, '.join(kw) + '=?'
        valueList = kw.values()
        valueList += (trove.jobId, trove.getName(),
                      trove.getVersion().freeze(),
                      trove.getFlavor().freeze(),
                      trove.getContext())

        cu.execute("""UPDATE BuildTroves
                      SET %s
                      WHERE jobId=? AND troveName=? AND version=? 
                            AND flavor=? AND context=?
                   """ % fieldList, valueList)
        troveId = self._getTroveId(cu, trove.jobId,
                                   *trove.getNameVersionFlavor(True))
        className, settings = freeze('TroveSettings', trove.settings)
        settings['_class'] = [className]
        cu.execute('DELETE FROM TroveSettings WHERE troveId=?', troveId)
        for key, values in settings.iteritems():
            for idx, value in enumerate(values):
                cu.execute('''INSERT INTO TroveSettings
                              (jobId, troveId, key, ord, value)
                              VALUES (?, ?, ?, ?, ?)''', trove.jobId, troveId,
                                                         key, idx, value)


    def UNPORTED_setBuildTroves(self, job):
        cu = self.db.cursor()
        cu.execute('DELETE FROM BuildTroves WHERE jobId=?', job.jobId)
        cu.execute('DELETE FROM TroveSettings WHERE jobId=?', job.jobId)
        for trove in job.iterTroves():
            self.addTrove(trove)

    def UNPORTED_addTrove(self, trove):
        cu = self.db.cursor()
        if not trove.logPath:
            trove.logPath = self.db.logStore.getTrovePath(trove)

        failureTup = freeze('FailureReason', trove.getFailureReason())
        if failureTup[0] == '':
            failureTup = None, None
        kw = dict(jobId=trove.jobId,
                  troveName=trove.getName(),
                  version=trove.getVersion().freeze(),
                  flavor=trove.getFlavor().freeze(),
                  pid=trove.pid,
                  start=trove.start,
                  finish=trove.finish,
                  logPath=trove.logPath,
                  recipeType=trove.recipeType,
                  status=trove.status,
                  state=trove.state,
                  failureReason=failureTup[0],
                  failureData=failureTup[1],
                  buildType=trove.buildType,
                  troveType=trove.troveType,
                  context=trove.getContext())
        fieldList = ', '.join(kw.keys())
        valueList = kw.values()
        qList = ','.join('?' for x in xrange(len(kw.keys())))

        cu.execute("""INSERT INTO BuildTroves
                      (%s) VALUES (%s)
                   """ % (fieldList, qList), valueList)
        troveId = cu.lastrowid
        className, settings = freeze('TroveSettings', trove.settings)
        settings['_class'] = [className]
        for key, values in settings.iteritems():
            for idx, value in enumerate(values):
                cu.execute('''INSERT INTO TroveSettings
                              (jobId, troveId, key, ord, value)
                              VALUES (?, ?, ?, ?, ?)''', trove.jobId, troveId,
                                                         key, idx, value)

    def UNPORTED_updateJobLog(self, job, message):
        cu = self.db.cursor()
        cu.execute("INSERT INTO StateLogs (jobId, message, args)"
                   " VALUES (?, ?, ?)",
                   (job.jobId, message, ''))
        return True

    def UNPORTED_updateTroveLog(self, trove, message):
        cu = self.db.cursor()
        troveId = self._getTroveId(cu, trove.jobId, 
                                   *trove.getNameVersionFlavor(True))
        cu.execute("INSERT INTO StateLogs (jobId, troveId, message, args)"
                   " VALUES (?, ?, ?, ?)",
                   (trove.jobId, troveId, message, ''))
        return True
