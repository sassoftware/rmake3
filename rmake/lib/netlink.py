#!/usr/bin/python
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


"""
Pure python netlink implementation, providing nice things like network
configuration without shelling out to system tools.
"""

import errno
import socket
import struct

from rmake.lib import netlink_support as nsp


class RoutingNetlink(object):
    """Retrieve network configuration details over a netlink socket."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW,
                nsp.NETLINK_ROUTE)
        self._seq = 0

    def getSeq(self):
        self._seq += 1
        return self._seq

    def send(self, msgtype, flags, seq, data, pid=0):
        self.sock.send(nsp.netlink_pack(msgtype, flags, seq, pid, data))

    def dumpNetInfo(self, msgtype, filter, family=0):
        """Send one NETLINK_ROUTE request and return a list of results."""
        seq = self.getSeq()
        self.send(msgtype,
                flags=nsp.NLM_F_ROOT | nsp.NLM_F_MATCH | nsp.NLM_F_REQUEST,
                seq=seq,
                data=struct.pack('Bxxx', family))

        out = []
        while True:
            data = self.sock.recv(1000000)
            for msgtype, flags, mseq, pid, data in nsp.netlink_unpack(data):
                if mseq != seq:
                    raise RuntimeError("seq mismatch")
                if msgtype == nsp.NLMSG_DONE:
                    return out
                elif msgtype == nsp.NLMSG_ERROR:
                    raise RuntimeError("rtnl error")
                elif msgtype == nsp.NLMSG_OVERRUN:
                    raise RuntimeError("rtnl overrun")
                elif msgtype in filter:
                    out.append(filter[msgtype](data))

    def getAllAddresses(self, raw=False):
        """Return a set of all useful inet and inet6 addresses.

        Doesn't include:
         * Loopback
         * Interfaces that are down
         * Addresses in local scope

        @param raw: If True, return the raw address bytes instead of a string
            form.
        @return: Set of (family, address, prefix) where family is "inet" or
            "inet6", address is a string, and prefix is the bit length of the
            network prefix.
        """
        links = {}
        for ifi in self.dumpNetInfo(msgtype=nsp.RTM_GETLINK,
                filter={nsp.RTM_NEWLINK: nsp.ifinfomsg_unpack}):
            links[ifi.index] = ifi

        addrs = {}
        for ifa in self.dumpNetInfo(msgtype=nsp.RTM_GETADDR,
                filter={nsp.RTM_NEWADDR: nsp.ifaddrmsg_unpack}):
            addrs.setdefault(ifa.index, []).append(ifa)

        out = set()
        for index, ifi in links.items():
            if ifi.flags & nsp.IFF_LOOPBACK:
                # Interface is lo
                continue
            if not (ifi.flags & nsp.IFF_UP):
                # Interface is down
                continue

            for ifa in addrs.get(ifi.index, {}):
                if ifa.scope >= nsp.RT_SCOPE_LINK:
                    # Link addresses aren't directly useful (the caller has to
                    # bind to the correct interface first) and anything smaller
                    # in scope than link isn't reachable outside of the local
                    # system.
                    continue
                address = ifa.attrs.get(nsp.IFA_ADDRESS)
                if not address:
                    continue
                if ifa.family == socket.AF_INET:
                    family = 'inet'
                elif ifa.family == socket.AF_INET6:
                    family = 'inet6'
                else:
                    continue
                if not raw:
                    address = socket.inet_ntop(ifa.family, address)
                out.add((family, address, ifa.prefixlen))

        return out


def main():
    rtnl = RoutingNetlink()
    for family, address, prefix in sorted(rtnl.getAllAddresses()):
        print family, '%s/%s' % (address, prefix)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except IOError, err:
        if err.errno != errno.EPIPE:
            raise
