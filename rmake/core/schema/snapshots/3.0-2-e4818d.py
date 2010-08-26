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
