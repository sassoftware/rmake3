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
