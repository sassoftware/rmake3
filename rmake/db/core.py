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


from rmake.core.types import RmakeJob, RmakeTask, JobStatus, JobTimes
from rmake.lib.ninamori.decorators import protected, protectedBlock, readOnly
from rmake.lib.ninamori.error import UniqueViolationError
from rmake.lib.ninamori.types import SQL
from rmake.lib.uuid import UUID


class CoreDB(object):

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _popStatus(kwargs):
        return JobStatus(kwargs.pop('status_code'), kwargs.pop('status_text'),
                kwargs.pop('status_detail'))

    @staticmethod
    def _popTimes(kwargs):
        return JobTimes(kwargs.pop('time_started'), kwargs.pop('time_updated'),
                kwargs.pop('time_finished'), kwargs.pop('expires_after', None),
                kwargs.pop('time_ticks', None))

    @readOnly
    def _getThings(self, cu, table, column, generator, raw_uuids):
        uuids = []
        for uuid in raw_uuids:
            if not isinstance(uuid, UUID):
                uuid = UUID(uuid)
            uuids.append(uuid)

        stmt = "SELECT * FROM %s WHERE %s IN %%s" % (table, column)
        cu.execute(stmt, (tuple(uuids),))

        things = dict(((getattr(x, column), x) for x in generator(cu)))
        return [things.get(x) for x in uuids]

    ## Jobs

    def _iterJobs(self, cu):
        for row in cu:
            kwargs = dict(row)
            kwargs['status'] = self._popStatus(kwargs)
            kwargs['times'] = self._popTimes(kwargs)
            del kwargs['frozen']
            yield RmakeJob(**kwargs)

    def getJobs(self, job_uuids):
        return self._getThings('jobs.jobs', 'job_uuid', self._iterJobs,
                job_uuids)

    @protected
    def createJob(self, cu, job):
        cu.execute("""
            INSERT INTO jobs.jobs ( job_uuid, job_type, owner, status_code,
                status_text, status_detail, expires_after )
            VALUES ( %s, %s, %s, %s, %s, %s, %s )
            RETURNING jobs.jobs.*
            """, (job.job_uuid, job.job_type, job.owner, job.status.code,
                job.status.text, job.status.detail, job.times.expires_after))
        return self._iterJobs(cu).next()

    @protected
    def updateJob(self, cu, job, frozen=None):
        stmt = SQL("""
            UPDATE jobs.jobs SET status_code = %s, status_text = %s,
                status_detail = %s, time_updated = now(), time_ticks = %s
                """, job.status.code, job.status.text, job.status.detail,
                job.times.ticks)
        if job.status.final:
            stmt += SQL(", time_finished = now(), frozen = NULL")
        elif frozen is not None:
            stmt += SQL(", frozen = %s", cu.binary(frozen))

        stmt += SQL("""
            WHERE job_uuid = %s AND time_ticks < %s
            RETURNING jobs.jobs.*
            """, job.job_uuid, job.times.ticks)
        cu.execute(stmt)
        try:
            return self._iterJobs(cu).next()
        except StopIteration:
            # No row updated
            return None

    ## Tasks

    def _iterTasks(self, cu):
        for row in cu:
            kwargs = dict(row)
            kwargs['status'] = self._popStatus(kwargs)
            kwargs['times'] = self._popTimes(kwargs)
            yield RmakeTask(**kwargs)

    def getTasks(self, task_uuids):
        return self._getThings('jobs.tasks', 'task_uuid', self._iterTasks,
                task_uuids)

    @protected
    def createTask(self, cu, task):
        cu.execute("""
            INSERT INTO jobs.tasks ( task_uuid, job_uuid, task_name, task_type,
                task_data, status_code, status_text, status_detail,
                node_assigned )
            VALUES ( %s, %s, %s, %s, %s, %s, %s, %s, %s )
            RETURNING jobs.tasks.*
            """, (task.task_uuid, task.job_uuid, task.task_name,
                task.task_type, task.task_data, task.status.code,
                task.status.text, task.status.detail, task.node_assigned))
        return self._iterTasks(cu).next()

    @protectedBlock
    def createTaskMaybe(self, task):
        # TODO: use a stored procedure
        try:
            return self.createTask(task)
        except UniqueViolationError:
            return self.getTasks([task.task_uuid])[0]

    @protected
    def updateTask(self, cu, task):
        stmt = SQL("""
            UPDATE jobs.tasks SET status_code = %s, status_text = %s,
                status_detail = %s, time_updated = now(), time_ticks = %s,
                node_assigned = %s
                """, task.status.code, task.status.text, task.status.detail,
                task.times.ticks, task.node_assigned)
        if task.status.final:
            stmt += SQL(", time_finished = now()")

        stmt += SQL("""
            WHERE task_uuid = %s AND time_ticks < %s
            RETURNING jobs.tasks.*
            """, task.task_uuid, task.times.ticks)
        cu.execute(stmt)
        try:
            return self._iterTasks(cu).next()
        except StopIteration:
            # No row updated
            return None
