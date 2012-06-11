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
