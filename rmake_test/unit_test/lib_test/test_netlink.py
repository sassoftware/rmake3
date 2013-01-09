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
