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


from rmake.lib import rpc_pickle
from rmake.lib import rpcproxy
from rmake.lib.twisted_extras import firehose


class BaseClient(object):

    def __init__(self, address):
        if isinstance(address, RmakeClient):
            # Copy an existing client's address
            address = address.address
        elif not isinstance(address, rpcproxy.Address):
            address = rpcproxy.parseAddress(address)
        self.address = address
        if hasattr(address, 'handler') and address.handler in ('', '/'):
            fh_address = address.copy()
            fh_address.handler = '/firehose'
            self.firehose = firehose.FirehoseClient(
                    fh_address.asString(withPassword=True))
            address = address.copy()
            address.handler = '/picklerpc'
        else:
            self.firehose = None
        self.proxy = rpc_pickle.PickleServerProxy(address)


class RmakeClient(BaseClient):

    def getJobs(self, job_uuids):
        return self.proxy.getJobs(job_uuids)

    def getJob(self, job_uuid):
        return self.proxy.getJobs([job_uuid])[0]

    def createJob(self, job, subscribe=False):
        sid = subscribe and self.firehose.sid or None
        return self.proxy.createJob(job, firehose=sid)

    def getWorkerList(self):
        return self.proxy.getWorkerList()

    def registerWorker(self, jid):
        return self.proxy.admin.registerWorker(jid)

    def deregisterWorker(self, jid):
        return self.proxy.admin.deregisterWorker(jid)
