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
