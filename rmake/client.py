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
