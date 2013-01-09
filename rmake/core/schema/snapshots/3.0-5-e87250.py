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


from rmake.lib.ninamori import error as nerror
from rmake.lib.ninamori import timeline
from rmake.lib.ninamori.decorators import protected


class Script(timeline.ScriptBase):

    def before(self):
        # Create plpgsql if it doesn't exist. It might be there due to being in
        # template1 or enabled by default in a future version of postgres.
        self.create_lang()

        # Test if a UUID type is available. If not, create it as a domain of
        # text.
        try:
            self.test_uuid()
        except nerror.UndefinedObjectError:
            self.create_uuid()

    @protected
    def create_lang(self, cu):
        cu.execute("SELECT COUNT(*) FROM pg_language WHERE lanname ='plpgsql'")
        if cu.fetchone()[0]:
            return
        cu.execute("CREATE LANGUAGE plpgsql")

    @protected
    def test_uuid(self, cu):
        cu.execute("SELECT 'uuid'::regtype")

    @protected
    def create_uuid(self, cu):
        cu.execute("CREATE DOMAIN uuid text")
