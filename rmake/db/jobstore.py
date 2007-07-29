#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

from conary.deps import deps
from conary import versions

from conary.deps.deps import ThawFlavor
from conary.versions import ThawVersion

from rmake.build import buildjob
from rmake.build import buildtrove

from rmake.build.buildtrove import TROVE_STATE_INIT
from rmake.build.buildjob import JOB_STATE_FAILED, JOB_STATE_INIT, \
     JOB_STATE_QUEUED, JOB_STATE_STARTED, JOB_STATE_BUILD, JOB_STATE_BUILT


from rmake.lib.apiutils import freeze, thaw

class JobStore(object):

    def __init__(self, db):
        self.db = db

    def isJobBuilding(self):
        cu = self.db.cursor()
        cu.execute("SELECT COUNT(*) FROM Jobs WHERE state in (?, ?)", 
                   JOB_STATE_BUILD, JOB_STATE_STARTED)
        return cu.fetchone()[0]

    def jobExists(self, jobId):
        cu = self.db.cursor()
        cu.execute("SELECT COUNT(*) FROM Jobs WHERE jobId=?", jobId)
        ret = cu.fetchone()[0]
        return ret

    def listJobs(self, activeOnly=False, jobLimit=None):
        cu = self.db.cursor()
        sql = """SELECT jobId FROM Jobs"""
        if activeOnly:
            sql += ' WHERE state in (%s)' % ','.join(str(x) for x in buildjob.ACTIVE_STATES)
        if jobLimit:
            sql += ' ORDER BY jobId DESC LIMIT %d' % jobLimit

        return [x[0] for x in cu.execute(sql)]

    def listTrovesByState(self, jobId, state=None):
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

    def getJob(self, jobId, withTroves=False, withConfigs=True):
        return self.getJobs([jobId], withTroves=withTroves, 
                            withConfigs=withConfigs)[0]

    def getJobs(self, jobIdList, withTroves=False, withConfigs=False):
        cu = self.db.cursor()
        cu.execute("""
        CREATE TEMPORARY TABLE tjobIdList(
            jobId INT
        )""", start_transaction=False)

        try:
            for jobId in jobIdList:
                cu.execute("INSERT INTO tJobIdList VALUES (?)",
                           jobId, start_transaction=False)
            results = cu.execute('''
                            SELECT tjobIdList.jobId, Jobs.uuid, state, status, 
                                   start, finish, failureReason, failureData,
                                   pid
                            FROM tJobIdList
                            LEFT JOIN Jobs USING(jobId)
                                 ''')

            jobsById = {}
            for (jobId, uuid, state, status, start,
                 finish, failureReason, failureData, pid) in results:
                if state is None:
                    # quick catch check for missing jobs
                    raise KeyError, jobId

                failureReason = thaw('FailureReason', 
                                     (failureReason, failureData))
                job = buildjob.BuildJob(jobId, status=status, state=state,
                                        start=float(start),
                                        finish=float(finish),
                                        failureReason=failureReason,
                                        uuid=uuid, pid=pid)
                jobsById[jobId] = job

            if withTroves:
                results = cu.execute(
                """
                    SELECT jobId, BuildTroves.troveId, troveName, version,
                        flavor, context, state, status, failureReason, 
                        failureData, start, finish, logPath, pid, recipeType, 
                        Chroots.path, Chroots.nodeName
                        FROM tJobIdList
                        JOIN BuildTroves USING(jobId)
                        LEFT JOIN Chroots USING(chrootId)
                """)

                trovesById = {}

                for (jobId, troveId, name, version, flavor, context,
                     state, status, failureReason, failureData, start, finish,
                     logPath, pid, recipeType,
                     chrootPath, chrootHost) in results:

                    if chrootPath is None:
                        chrootPath = ''
                        chrootHost = ''
                    version = versions.ThawVersion(version)
                    flavor = ThawFlavor(flavor)
                    failureReason = thaw('FailureReason',
                                         (failureReason, failureData))
                    buildTrove = buildtrove.BuildTrove(jobId, name, version, 
                                               flavor,
                                               state=state, start=float(start),
                                               finish=float(finish),
                                               logPath=logPath, status=status,
                                               failureReason=failureReason,
                                               pid=pid, recipeType=recipeType,
                                               chrootPath=chrootPath,
                                               chrootHost=chrootHost,
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
            else:
                results = cu.execute('''
                SELECT BuildTroves.jobId, troveName, version, flavor
                    FROM tJobIdList
                    JOIN BuildTroves USING(jobId)
                ''')
                for (jobId, n,v,f) in results:
                    jobsById[jobId].addTrove(n, versions.ThawVersion(v), ThawFlavor(f))
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
                for jobId, configDict in jobConfigD.items():
                    configDict = dict((x[0], thaw('BuildConfiguration', x[1]))
                                       for x in configD.iteritems())
                    jobsById[jobId].setConfigs(configDict)
            return [jobsById[jobId] for jobId in jobIdList]
        finally:
            cu.execute("DROP TABLE tJobIdList", start_transaction = False)

    def _getTroveId(self, cu, jobId, name, version, flavor, context=''):
        cu.execute(
            '''
            SELECT troveId
                FROM BuildTroves
                WHERE jobId=? AND troveName=? AND version=?  AND flavor=? AND context=?
            ''',
            jobId, name, version.freeze(), flavor.freeze(), context)

        return self.db._getOne(cu, (jobId, name, version, flavor))[0]

    def getJobsByState(self, state, withTroves=False):
        cu = self.db.cursor()
        jobIds = cu.execute('SELECT jobId FROM Jobs WHERE state=?',
                            state).fetchall()
        return self.getJobs([x[0] for x in jobIds], withTroves=withTroves)

    def getJobIdsFromUUIDs(self, uuids):
        cu = self.db.cursor()
        # would a temporary table be more efficient?  I'm not sure
        jobIds = []
        for uuid in uuids:
            cu.execute('''SELECT jobId FROM Jobs where uuid=?''', uuid)
            jobIds.append(self.db._getOne(cu, uuid)[0])
        return jobIds

    def getTrove(self, jobId, name, version, flavor, context=''):
        return self.getTroves([(jobId, name, version, flavor, context)])[0]

    def getTroves(self, troveList):
        cu = self.db.cursor()
        cu.execute('''CREATE TEMPORARY TABLE tTroveInfo(
                          jobId INT,
                          troveName STR,
                          version STR,
                          flavor STR,
                          context STR
                      )''', start_transaction=False)

        for jobId, troveName, version, flavor, context in troveList:
            cu.execute('''INSERT INTO tTroveInfo VALUES (?, ?, ?, ?, ?)''',
                       (jobId, troveName, version.freeze(), flavor.freeze(),
                       context), start_transaction=False)

        results = cu.execute(
        """
            SELECT BuildTroves.troveId, jobId, pid, troveName, version,
                flavor, context, state, status, failureReason, failureData,
                start, finish, logPath, recipeType,
                Chroots.nodeName, Chroots.path
                FROM tTroveInfo
                JOIN BuildTroves USING(jobId, troveName, version, flavor, context)
                LEFT JOIN Chroots USING(chrootId)
        """)

        trovesById = {}
        trovesByNVF = {}
        # FIXME From here on out it's mostly duplication from getJobs code
        for (troveId, jobId, pid, troveName, version, flavor, context, state, 
             status, failureReason, failureData, start, finish, logPath, 
             recipeType, chrootHost, chrootPath) \
             in results:
            if chrootPath is None:
                chrootPath = chrootHost = ''
            version = versions.ThawVersion(version)
            flavor = ThawFlavor(flavor)
            failureReason = thaw('FailureReason',
                                 (failureReason, failureData))
            buildTrove = buildtrove.BuildTrove(jobId, troveName, version,
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
                JOIN BuildTroves USING(jobId, troveName, version, flavor)
                JOIN BinaryTroves USING(troveId)
        """)

        builtTroves = {}
        for troveId, troveName, version, flavor in results:
            builtTroves.setdefault(troveId, []).append((
                    troveName, ThawVersion(version), ThawFlavor(flavor)))
        for troveId, binTroves in builtTroves.iteritems():
            trovesById[troveId].setBuiltTroves(binTroves)

        cu.execute("DROP TABLE tTroveInfo", start_transaction = False)
        return [trovesByNVF[x] for x in troveList]


    # return all the log messages since last mark
    def getJobLogs(self, jobId, mark = 0):
        cu = self.db.cursor()
        ret = []
        cu.execute("""
        SELECT changed, message, args FROM StateLogs
        WHERE jobId = ? AND troveId=0 ORDER BY logId LIMIT ? OFFSET ?
        """, (jobId, 100, mark))
        return cu.fetchall()

    # return all the log messages since last mark
    def getTroveLogs(self, jobId, troveTuple, mark = 0):
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

    def getJobConfig(self, jobId):
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

    def addJob(self, job):
        cu = self.db.cursor()
        cu.execute("INSERT INTO Jobs (jobId, uuid, state) VALUES (NULL, ?, ?)", 
                   job.uuid, job.state)
        jobId = cu.lastrowid
        for troveName, version, flavor, context in job.iterTroveList(True):
            cu.execute("INSERT INTO BuildTroves "
                       "(jobId, troveName, version, flavor, state, context) "
                       "VALUES (?, ?, ?, ?, ?, ?)", (
                jobId, troveName, version.freeze(),
                flavor.freeze(), TROVE_STATE_INIT, context))
        for trove in job.iterTroves():
            trove.jobId = jobId
        for context, jobConfig in job.getConfigDict().items():
            self.addJobConfig(jobId, context, jobConfig)
        self.db.commit()
        job.jobId = jobId
        return jobId

    def deleteJobs(self, jobIdList):
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
        return troveList

    def addJobConfig(self, jobId, context, jobConfig):
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

    def setBinaryTroves(self, buildTrove, troveList):
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

    def updateJob(self, job):
        cu = self.db.cursor()
        failureTup = freeze('FailureReason', job.getFailureReason())
        cu.execute("""UPDATE Jobs set pid = ?, state = ?, status = ?, 
                                      start = ?, finish = ?, failureReason = ?, 
                                      failureData = ?
                       WHERE jobId = ?""",
                   (job.pid, job.state, job.status, job.start, job.finish, 
                    failureTup[0], failureTup[1], job.jobId))

    def updateTrove(self, trove):
        cu = self.db.cursor()

        if trove.getChrootHost():
            chrootId = self.db._getChrootIdForTrove(trove)
        else:
            chrootId = 0

        failureTup = freeze('FailureReason', trove.getFailureReason())
        kw = dict(pid=trove.pid, 
                  start=trove.start,
                  finish=trove.finish,
                  logPath=trove.logPath,
                  status=trove.status,
                  state=trove.state,
                  failureReason=failureTup[0],
                  failureData=failureTup[1],
                  recipeType=trove.recipeType,
                  chrootId=chrootId)
        fieldList = '=?, '.join(kw) + '=?'
        valueList = kw.values()
        valueList += (trove.jobId, trove.getName(),
                      trove.getVersion().freeze(),
                      trove.getFlavor().freeze(),
                      trove.getContext())

        cu.execute("""UPDATE BuildTroves
                      SET %s
                      WHERE jobId=? AND troveName=? AND version=? AND flavor=? AND context=?
                   """ % fieldList, valueList)

    def setBuildTroves(self, job):
        cu = self.db.cursor()
        cu.execute('DELETE FROM BuildTroves WHERE jobId=?', job.jobId)
        for trove in job.iterTroves():
            self.addTrove(trove)

    def addTrove(self, trove):
        cu = self.db.cursor()
        if not trove.logPath:
            trove.logPath = self.db.logStore.getTrovePath(trove)

        failureTup = freeze('FailureReason', trove.getFailureReason())
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
                  context=trove.getContext())
        fieldList = ', '.join(kw.keys())
        valueList = kw.values()
        qList = ','.join('?' for x in xrange(len(kw.keys())))

        cu.execute("""INSERT INTO BuildTroves
                      (%s) VALUES (%s)
                   """ % (fieldList, qList), valueList)

    def updateJobLog(self, job, message):
        cu = self.db.cursor()
        cu.execute("INSERT INTO StateLogs (jobId, troveId, message, args)"
                   " VALUES (?, 0, ?, ?)",
                   (job.jobId, message, ''))
        return True

    def updateTroveLog(self, trove, message):
        cu = self.db.cursor()
        troveId = self._getTroveId(cu, trove.jobId, 
                                   *trove.getNameVersionFlavor(True))
        cu.execute("INSERT INTO StateLogs (jobId, troveId, message, args)"
                   " VALUES (?, ?, ?, ?)",
                   (trove.jobId, troveId, message, ''))
        return True


class JobQueue(object):

    def __init__(self, db):
        self.db = db

    def add(self, job):
        cu = self.db.cursor()
        cu.execute('INSERT INTO JobQueue VALUES (?)', job.jobId)

    def pop(self):
        cu = self.db.cursor()
        cu.execute('SELECT jobId FROM JobQueue ORDER BY jobId ASC LIMIT 1')
        results = cu.fetchall()
        if results:
            jobId = results[0][0]
            cu.execute('DELETE FROM JobQueue WHERE jobID=?', jobId)
            return jobId
        else:
            raise IndexError, 'Queue is empty'

    def isEmpty(self):
        cu = self.db.cursor()
        return cu.execute('SELECT COUNT(*) FROM JobQueue').fetchall()[0]


