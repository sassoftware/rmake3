#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
from rmake.lib import apirpc
from rmake.lib.apiutils import api, api_parameters, api_return

class ServerExtension(apirpc.ApiServer):

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def listNodes(self, callData):
        raise NotImplementedError

    @api(version=1)
    @api_parameters(1)
    @api_return(1, None)
    def getMessageBusInfo(self, callData):
        raise NotImplementedError
