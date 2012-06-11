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
