#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
"""
Rmake-specific errors.
"""
from conary.lib import util

from conary.errors import ParseError # make ParseError available from 
                                     # rmake as well

from rmake.lib import apiutils

class RmakeInternalError(Exception):
    pass

class RmakeError(Exception):
    """
        RmakeError - superclass for all well-defined rMake errors.

        If you create an error in rMake, it should derive from this class,
        and have a str() that is acceptable output for the command line,
        with an "error: " prompt before it.

        Any relevant data for this error should be stored outside of the
        string so it can be accessed from non-command-line interfaces.
    """
    @classmethod
    def __thaw__(class_, data):
        return class_(*data)

    def __freeze__(self):
        return self.args
apiutils.register(RmakeError)

class BadParameters(RmakeError):
    """
        Raised when a command is given bad parameters at the command line.
    """
    pass

class JobNotFound(RmakeError):
    def __str__(self):
        return "JobNotFound: Could not find job with jobId %s" % self.args[0]

    @classmethod
    def __thaw__(class_, data):
        return class_(*data)

    def __freeze__(self):
        return self.args
apiutils.register(JobNotFound)

class TroveNotFound(RmakeError):
    def __str__(self):
        return "TroveNotFound: Could not find trove %s=%s[%s] with jobId %s" % (self.args[1:] + self.args[0:1])

    @classmethod
    def __thaw__(class_, data):
        return class_(data[0], *thaw('troveTuple', data[1]))

    def __freeze__(self):
        return (self.args[0], freeze('troveTuple', self.args[1:]))
apiutils.register(JobNotFound)


class DatabaseSchemaTooNew(RmakeError):
    def __init__(self):
        RmakeError.__init__(self,
            """The rmake database is too new for the version of rmake you are running.""")



class ServerError(RmakeError):
    """
        Generic error for communicating with the rMakeServer.
    """
    pass

class OpenError(ServerError):
    """
        Generic error for starting communication with the rMakeServer.
    """
    pass



# error that gets output when a Python exception makes it to the command 
# line.
errorMessage = '''
*******************************************************************
*** An error has occurred in rmake:
***
*** %(filename)s:%(lineno)s
*** %(errtype)s: %(errmsg)s
***
*** Receiving this message is always a due to a bug in rmake, not
*** user error.
***
*** The related traceback has been output to %(stackfile)s
***
*** To get a debug prompt, rerun this command with the --debug-all flag.
***
*** For more debugging help, please go to #conary on freenode.net
*** or email conary-list@lists.rpath.com.
***
*******************************************************************

'''

def genExcepthook(*args, **kw):
    return util.genExcepthook(error=errorMessage,
                              prefix='rmake-error-', *args, **kw)

uncatchableExceptions = (KeyboardInterrupt, SystemExit)
