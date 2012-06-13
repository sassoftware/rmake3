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
