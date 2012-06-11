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
Constants and structures for dealing with netlink sockets.
"""

import struct
from conary.lib.compat import namedtuple


## linux/netlink.h
STRUCT_NLMSGHDR = 'IHHII'

NETLINK_ROUTE           = 0

# Core message types
NLMSG_NOOP, NLMSG_ERROR, NLMSG_DONE, NLMSG_OVERRUN = range(1, 5)

# Flags values
NLM_F_REQUEST           = 0x001
NLM_F_MULTI             = 0x002
NLM_F_ACK               = 0x004
NLM_F_ECHO              = 0x010

# Modifiers to GET request
NLM_F_ROOT              = 0x100
NLM_F_MATCH             = 0x200
NLM_F_ATOMIC            = 0x400
NLM_F_DUMP              = (NLM_F_ROOT | NLM_F_MATCH)


def netlink_pack(msgtype, flags, seq, pid, data):
    """Pack a single netlink packet."""
    return struct.pack(STRUCT_NLMSGHDR, 16 + len(data),
            msgtype, flags, seq, pid) + data


def netlink_unpack(data):
    """Unpack a sequence of netlink packets."""
    out = []
    while data:
        length, msgtype, flags, seq, pid = struct.unpack(STRUCT_NLMSGHDR,
                data[:16])
        if len(data) < length:
            raise RuntimeError("Buffer overrun!")
        out.append((msgtype, flags, seq, pid, data[16:length]))
        data = data[length:]
    return out


## linux/rtnetlink.h
RTM_NEWLINK, RTM_DELLINK, RTM_GETLINK, RTM_SETLINK = range(16, 20)
RTM_NEWADDR, RTM_DELADDR, RTM_GETADDR = range(20, 23)

RT_SCOPE_LINK           = 253

STRUCT_RTATTR = 'HH'


def rtattr_unpack(data):
    """Unpack a sequence of netlink attributes."""
    size = struct.calcsize(STRUCT_RTATTR)
    attrs = {}
    while data:
        rta_len, rta_type = struct.unpack(STRUCT_RTATTR, data[:size])
        assert len(data) >= rta_len
        rta_data = data[size:rta_len]
        padded = ((rta_len + 3) / 4) * 4
        attrs[rta_type] = rta_data
        data = data[padded:]
    return attrs


## linux/if.h

IFF_UP                  = 0x001
IFF_LOOPBACK            = 0x008


## linux/if_link.h

STRUCT_IFINFOMSG = 'BxHiII'
IfInfoMsg = namedtuple('IfInfoMsg', 'family type index flags change attrs')

(IFLA_UNSPEC, IFLA_ADDRESS, IFLA_BROADCAST, IFLA_IFNAME, IFLA_MTU, IFLA_LINK,
        IFLA_QDISC, IFLA_STATS, IFLA_COST, IFLA_PRIORITY, IFLA_MASTER,
        IFLA_WIRELESS, IFLA_PROTINFO, IFLA_TXQLEN, IFLA_MAP, IFLA_WEIGHT,
        IFLA_OPERSTATE, IFLA_LINKMODE, IFLA_LINKINFO, IFLA_NET_NS_PID,
        IFLA_IFALIAS, IFLA_NUM_VF, IFLA_VFINFO_LIST, IFLA_STATS64,
        IFLA_VF_PORTS, IFLA_PORT_SELF,) = range(26)


def ifinfomsg_unpack(data):
    """Unpack struct ifinfomsg and its attributes."""
    size = struct.calcsize(STRUCT_IFINFOMSG)
    family, type, index, flags, change = struct.unpack(STRUCT_IFINFOMSG,
            data[:size])
    attrs = rtattr_unpack(data[size:])
    return IfInfoMsg(family, type, index, flags, change, attrs)


## linux/if_addr.h

STRUCT_IFADDRMSG = '4BI'
IfAddrMsg = namedtuple('IfAddrMsg', 'family prefixlen flags scope index attrs')

(IFA_UNSPEC, IFA_ADDRESS, IFA_LOCAL, IFA_LABEL, IFA_BROADCAST, IFA_ANYCAST,
        IFA_CACHEINFO, IFA_MULTICAST) = range(8)


def ifaddrmsg_unpack(data):
    """Unpack struct ifaddrmsg and its attributes."""
    size = struct.calcsize(STRUCT_IFADDRMSG)
    family, prefixlen, flags, scope, index = struct.unpack(STRUCT_IFADDRMSG,
            data[:size])
    attrs = rtattr_unpack(data[size:])
    return IfAddrMsg(family, prefixlen, flags, scope, index, attrs)
