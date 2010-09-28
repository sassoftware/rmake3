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


# Status codes for a job
JOB_OK                      = 200
JOB_FAILED                  = 400

# Status codes for a task
TASK_OK                     = 200
TASK_FAILED                 = 400
TASK_NOT_ASSIGNABLE         = 401

# "ok" code for WorkerInfo.getScore() -- when can this task be assigned?
A_NOW                       = 0
A_LATER                     = 1
A_NEVER                     = 2
A_WRONG_ZONE                = 3
