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


from twisted.trial import unittest

from rmake.lib import netlink


class NetlinkTest(unittest.TestCase):

    def test_scope_filter(self):
        """Ensure that no loopback or link-scope addresses are returned."""
        rtnl = netlink.RoutingNetlink()
        addrs = rtnl.getAllAddresses(raw=True)

        # I guess this won't work on machines with no networking, but it's more
        # valuable to prove that something happened.
        assert addrs

        for family, address, prefix in addrs:
            if family == 'inet':
                # No loopback
                assert address[0] != chr(127)
            elif family == 'inet6':
                # No loopback
                assert address != '\0\0\0\0\0\0\0\1'
                # No link-local
                assert address[:2] != '\xfe\x80'
            else:
                self.fail("Invalid family " + family)
