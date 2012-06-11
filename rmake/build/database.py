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
This module holds the database interface used by the trove build system, as an
extension of the core build system.
"""


class JobStore(object):

    def __init__(self, pool):
        self.pool = pool

    def createJob(self, cu, job):
        """Add build-specific data to the appropriate table after creating the
        core job object.

        This also assigns the job its jobId.

        NB: builds.jobs only holds things that need to be indexed and searched
        on without unpickling the job blob in the core jobs table.
        """
        ret = []
        d = cu.execute("""INSERT INTO build.jobs ( job_uuid, job_name )
                VALUES ( %s, %s ) RETURNING job_id """,
                (job.jobUUID, job.jobName))
        d.addCallback(lambda _: ret.append(cu.fetchone()[0]))

        for trove in job.iterTroves():
            d.addCallback(lambda _: cu.execute("""INSERT INTO build.job_troves
                    ( job_uuid, source_name, source_version,
                    build_flavor, build_context )
                VALUES ( %s, %s, %s, %s, %s )""",
                (job.jobUUID, trove.name, trove.version.freeze(),
                    trove.flavor.freeze(), trove.context)))

        # Just return the new jobId
        d.addCallback(lambda _: ret[0])
        return d
