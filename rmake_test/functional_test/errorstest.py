#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

from rmake_test import rmakehelp

from rmake import errors

class ErrorsTest(rmakehelp.RmakeHelper):
    def testErrors(self):
        client = self.getRmakeHelper()
        try:
            client.client.getJob(1)
        except errors.JobNotFound, err:
            assert(str(err) == 'JobNotFound: Could not find job with jobId 1')
        else:
            assert(False)
        client.client.uri.server._close()

