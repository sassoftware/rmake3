#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
from rmake.lib import apiutils
from rmake.lib.apiutils import freeze, thaw


class Chroot(object):
    def __init__(self, host, path, jobId, troveTuple, active):
        self.host = host
        self.path = path
        if not jobId:
            jobId = 0
        self.jobId = jobId
        self.troveTuple = troveTuple
        self.active = active

    def __freeze__(self):
        d = self.__dict__.copy()
        if self.troveTuple:
            d['troveTuple'] = freeze('troveTuple', self.troveTuple)
        else:
            d['troveTuple'] = ''
        return d

    @classmethod
    def __thaw__(class_, d):
        self = class_(**d)
        if self.troveTuple:
            self.troveTuple = thaw('troveTuple', self.troveTuple)
        else:
            self.troveTuple = None
        return self
apiutils.register(Chroot)
