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
