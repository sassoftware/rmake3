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


from rmake.core.types import RmakeJob, JobStatus, JobTimes
from rmake.lib.ninamori.decorators import protected, readOnly
from rmake.lib.ninamori.types import SQL
from rmake.lib.uuid import UUID


class CoreDB(object):

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _iterJobs(cu):
        for (job_uuid, job_type, owner, status_code, status_text,
                status_detail, time_started, time_updated, time_finished,
                expires_after) in cu:
            yield RmakeJob(job_uuid, job_type, owner,
                    JobStatus(status_code, status_text, status_detail),
                    JobTimes(time_started, time_updated, time_finished,
                        expires_after))

    @readOnly
    def getJobs(self, cu, job_uuids):
        uuids = []
        for uuid in job_uuids:
            if not isinstance(uuid, UUID):
                uuid = UUID(uuid)
            uuids.append(uuid)

        cu.execute("""
            SELECT job_uuid, job_type, owner, status_code, status_text,
                status_detail, time_started, time_updated, time_finished,
                expires_after
            FROM jobs.jobs WHERE job_uuid IN %s
            """, (tuple(uuids),))

        jobs = dict((x.job_uuid, x) for x in self._iterJobs(cu))
        return [jobs.get(x) for x in job_uuids]

    @protected
    def createJob(self, cu, job):
        cu.execute("""
            INSERT INTO jobs.jobs ( job_uuid, job_type, owner, status_code,
                status_text, status_detail, expires_after )
            VALUES ( %s, %s, %s, %s, %s, %s, %s )
            RETURNING job_uuid, job_type, owner, status_code, status_text,
                status_detail, time_started, time_updated, time_finished,
                expires_after
            """, (job.job_uuid, job.job_type, job.owner, job.status.code,
                job.status.text, job.status.detail, job.times.expires_after))
        return self._iterJobs(cu).next()

    @protected
    def updateJob(self, cu, job, frozen=None, isDone=False):
        stmt = SQL("""
            UPDATE jobs.jobs SET status_code = %s, status_text = %s,
                status_detail = %s, time_updated = now()
                """, job.status.code, job.status.text, job.status.detail)
        if isDone:
            stmt += SQL(", time_finished = now(), frozen = NULL")
        elif frozen is not None:
            stmt += SQL(", frozen = %s", cu.binary(frozen))

        stmt += SQL(" WHERE job_uuid = %s", job.job_uuid)
        cu.execute(stmt)
