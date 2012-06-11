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


import os
import socket


def getUptime():
    # second number is amount of time system has been idle since reboot.
    return float(open('/proc/uptime').read().strip().split()[0])

def getLoadAverage():
    # The fourth number is the number of running processes / total number of 
    # processes.
    # The fifth number is the highest PID used.
    data = open('/proc/loadavg').read().strip().split()[0:3]
    return tuple(float(x) for x in data)

def getCpuInfo():
    f = open("/proc/cpuinfo")
    parts = f.read().strip().split("\n\n")
    f.close()
    cpus = []
    for p in parts:
        lines = p.strip().split("\n")
        lines = [ l.split(":", 1) for l in lines ]
        cpuDict = dict( (key.strip(), val.strip()) for (key, val) in lines )
        cpus.append(CPUInfo(cpuDict["cpu MHz"], cpuDict["model name"]))
    return cpus

#def getStatInfo():
#    Get information about disk I/O, niced processes, etc.
#    open('/proc/stat') # http://www.linuxhowtos.org/System/procstat.htm

def getMountInfo():
    txt = os.popen('/bin/df -TP -x fuse.gvfs-fuse-daemon -x cifs '
            '2>/dev/null').read()
    lines = txt.split('\n')[1:-1]
    mounts = {}
    for cols in (x.split(None, 6) for x in lines if x):
        device, type, blocks, used, avail, capacity, mount = cols
        if device == 'none':
            device = None
        mounts[mount] = Partition(device, type, blocks, used, avail)
    return mounts

def getMemInfo():
    f = open("/proc/meminfo")
    lines = f.read().strip().split("\n")
    f.close()
    lines = [ l.split(None, 1) for l in lines ]
    memDict = dict( (key, val.strip().split()[0]) for (key, val) in lines )
    totalMemory = int(memDict["MemTotal:"])
    freeMemory = int(memDict["MemFree:"])
    totalSwap = int(memDict["SwapTotal:"])
    freeSwap = int(memDict["SwapFree:"])
    return (freeMemory, totalMemory), (freeSwap, totalSwap)


def getNetName():
    """
    Find a hostname or IP suitable for representing ourselves to clients.
    """
    for (so_fam, addr) in [
            # These addresses are on the public internet, although they don't
            # necessarily point anywhere.
            (socket.AF_INET, '8.8.8.8'),
            (socket.AF_INET6, '2001:4800::')]:
        try:
            # "connecting" a DGRAM socket doesn't do anything but bind to an
            # interface, which is exactly what we want.
            s = socket.socket(so_fam, socket.SOCK_DGRAM)
            s.connect((addr, 0))
            return s.getsockname()[0]
        except socket.error:
            pass

    # No default route or no IP, but at least local operations will work.
    return 'localhost'


class CPUInfo(object):
    def __init__(self, freq, model):
        self.freq = freq
        self.model = model

    @classmethod
    def __thaw__(class_, d):
        return class_(**d)

    def __freeze__(self):
        return self.__dict__

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

class Partition(object):
    def __init__(self, device, type, blocks, used, avail):
        self.device = device
        self.type = type
        self.blocks = blocks
        self.used = used
        self.avail = avail

    def __repr__(self):
        return "Partition(device=%r, type=%r, blocks=%r, used=%r, avail=%r)" \
                 % (self.device, self.type, self.blocks, self.used, self.avail)

    def __str__(self):
        return "%sK  (%sK free)" % (self.blocks, self.avail)

    @classmethod
    def __thaw__(class_, d):
        return class_(**d)

    def __freeze__(self):
        return self.__dict__

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

class MachineInformation(object):
    def __init__(self):
        self.hostname = os.uname()[1]
        self.cpus = getCpuInfo()
        self.update()

    def update(self):
        self.mounts = getMountInfo()
        self.meminfo = getMemInfo()
        self.loadavg = getLoadAverage()
        self.uptime = getUptime()

    def getLoadAverage(self, minutes):
        if minutes not in (1,5,15):
            raise ValueError('Can only get the load average for 1,5,or 15 minutes')
        if minutes == 1:
            return self.loadavg[0]
        if minutes == 5:
            return self.loadavg[1]
        if minutes == 15:
            return self.loadavg[2]

    def __str__(self):
        l = []
        l.append('Machine: %s' % self.hostname)
        l.append('CPUs: %s' % (len(self.cpus)))
        for idx, cpu in enumerate(self.cpus):
            l.append('  %s: %sMhz %s' % (idx, cpu.freq, cpu.model))
        l.append('Memory: %sK (%sK Free)' % self.meminfo[0])
        l.append('Swap: %sK (%sK Free)' % self.meminfo[1])
        l.append('')
        l.append('Load Average: %s (now) %s (5m) %s (15m)' % self.loadavg)
        l.append('Uptime: %ss' % self.uptime)
        l.append('Mounts:')
        l.extend(self.formatMountInfo())
        return '\n'.join(l)


    def formatMountInfo(self):
        l = []
        for mount, part in sorted(self.mounts.iteritems()):
            l.append("%-20s%s" % (mount + ':', part))
        return l

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    @classmethod
    def __thaw__(class_, d):
        self = class_()
        self.__dict__.update(d)
        self.cpus = [ CPUInfo.__thaw__(x) for x in self.cpus ]
        self.mounts = dict((x[0], Partition.__thaw__(x[1]))
                            for x in self.mounts)
        return self

    def __freeze__(self):
        d = self.__dict__.copy()
        d['cpus'] = [ x.__freeze__() for x in self.cpus ]
        d['mounts'] = [ (x[0], x[1].__freeze__())
                        for x in self.mounts.items() ]
        return d


if __name__ == "__main__":
    print MachineInformation()
