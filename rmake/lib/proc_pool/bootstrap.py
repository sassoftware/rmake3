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
