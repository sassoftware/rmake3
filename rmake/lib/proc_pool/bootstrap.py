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

import logging
import os
import sys
from twisted.internet import stdio
from twisted.python import reflect
from rmake.lib import logger
from rmake.lib.proc_pool import connector


def main(childClassName):
    from twisted.internet import reactor

    logger.setupLogging(withTwisted=True, consoleLevel=logging.INFO)

    # setpgrp prevents Ctrl-C at the command line from killing workers
    # directly.  Instead, the parent process catches the signal, flags all the
    # workers as shutting down, and kills the workers itself. This way no
    # exception is raised if the workers terminate abruptly.
    os.setpgrp()

    childClass = reflect.namedAny(childClassName)
    child = childClass()
    stdio.StandardIO(child, connector.TO_CHILD, connector.FROM_CHILD)

    reactor.run()


main(sys.argv[1])
