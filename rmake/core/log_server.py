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


import logging
import os
from twisted.application import service as ta_service
from twisted.internet import abstract as ti_abstract
from twisted.internet import interfaces as ti_interfaces
from twisted.python import filepath as tp_filepath
from twisted.web import http as tw_http
from twisted.web import static as tw_static
from zope.interface import implements

log = logging.getLogger(__name__)


class LogTreeManager(ta_service.Service):

    def __init__(self, basePath):
        self.top = LogResource(basePath, defaultType='text/plain')
        self.top.manager = self
        self.activeNodes = {}
        self.subscribers = {}

    def _subPath(self, path):
        if isinstance(path, basestring):
            assert path[0] == '/'
            path = tp_filepath.FilePath(path)
        segments = path.segmentsFrom(self.top)
        return os.sep.join(segments)

    def setNodeActive(self, path, active):
        """
        Active nodes can be tailed; inactive nodes are considered 'final' and
        behave like static resources.
        """
        subPath = self._subPath(path)
        if active:
            self.activeNodes[subPath] = True
        else:
            self.activeNodes.pop(subPath, None)
            subscribers = self.subscribers.pop(subPath, ())
            for subscriber in subscribers:
                subscriber.finish()

    def touchNode(self, path):
        """
        Call this after a node has been updated to push the new content out to
        subscribers.
        """
        subPath = self._subPath(path)
        subscribers = self.subscribers.get(subPath, ())
        for subscriber in subscribers:
            subscriber.produce()

    def isNodeActive(self, path):
        subPath = self._subPath(path)
        return self.activeNodes.get(subPath, False)

    def subscribeToNode(self, path, producer):
        subPath = self._subPath(path)
        self.subscribers.setdefault(subPath, []).append(producer)

    def unsubscribeFromNode(self, path, producer):
        subPath = self._subPath(path)
        subscribers = self.subscribers.get(subPath, ())
        if producer in subscribers:
            subscribers.remove(producer)

    def getResource(self):
        return self.top


class LogResource(tw_static.File):

    def createSimilarFile(self, path):
        obj = tw_static.File.createSimilarFile(self, path)
        obj.manager = self.manager
        return obj

    def directoryListing(self):
        return self.childNotFound

    def render_TAIL(self, request):
        return self.render_GET(request)

    def makeProducer(self, request, fobj):
        if request.method == 'TAIL' and self.manager.isNodeActive(self):
            # TODO: accept a single range, as a point to start tailing
            self._setContentHeaders(request, size=-1)
            request.setResponseCode(tw_http.OK)
            producer = FollowingProducer(request, fobj)
            self.manager.subscribeToNode(self, producer)
            d = request.notifyFinish()
            @d.addBoth
            def _cleanup(_):
                self.manager.unsubscribeFromNode(self, producer)
            return producer
        else:
            return tw_static.File.makeProducer(self, request, fobj)

    def _setContentHeaders(self, request, size=None):
        tw_static.File._setContentHeaders(self, request, size)
        if size == -1:
            # When tailing, length is not known ahead of time
            request.responseHeaders.removeHeader('content-length')


class FollowingProducer(object):

    implements(ti_interfaces.IPushProducer)

    bufferSize = ti_abstract.FileDescriptor.bufferSize

    def __init__(self, request, fobj):
        self.request = request
        self.fobj = fobj
        self.producing = True
        self.started = False
        self.finished = False

    def start(self):
        self.started = True
        self.produce()

    def resumeProducing(self):
        """Client buffer is ready for data"""
        self.producing = True
        self.produce()

    def pauseProducing(self):
        """Client buffer is full"""
        self.producing = False

    def finish(self):
        """File is complete; stop tailing"""
        self.finished = True
        self.produce()

    def produce(self):
        while self.started and self.producing:
            data = self.fobj.read(self.bufferSize)
            if data:
                self.request.write(data)
            else:
                if self.finished:
                    self.request.unregisterProducer()
                    self.request.finish()
                    self.stopProducing()
                break

    def stopProducing(self):
        """Client disconnected"""
        self.producing = False
        self.fobj.close()
        self.request = None
