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


# Status codes for a job
# Generic success
JOB_OK                      = 200
# Generic failure. Core failure codes will be in the range 450-499 and 550-599.
# All others are reserved for plugins.
JOB_FAILED                  = 450

# Status codes for a task
TASK_OK                     = 200
# See above note about core failure codes.
TASK_FAILED                 = 450
TASK_NOT_ASSIGNABLE         = 451

# "ok" code for WorkerInfo.getScore() -- when can this task be assigned?
A_NOW                       = 0
A_LATER                     = 1
A_NEVER                     = 2
A_WRONG_ZONE                = 3
