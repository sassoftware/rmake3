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
import urlparse
import xmlrpclib


class RbuilderClient(object):
    def __init__(self, rbuilderUrl, user, pw):
        scheme, netloc, path, query, fragment = urlparse.urlsplit(rbuilderUrl)

        path = os.path.join(path, 'xmlrpc-private')
        netloc = netloc.rsplit('@', 1)[-1]
        netloc = '%s:%s@' % (user, pw) + netloc

        # The query and fragment are not useful to XMLRPC, so null
        # those out.
        rbuilderUrl = urlparse.urlunsplit((scheme, netloc, path, '', ''))
        self.server = xmlrpclib.ServerProxy(rbuilderUrl)

    def getBuild(self, buildId):
        error, result = self.server.getBuild(buildId)
        if error:
            raise RuntimeError(*result)
        return result

    def newBuildWithOptions(self, productName, groupName, groupVersion,
                            groupFlavor, buildType, buildName, options):
        error, productId = self.server.getProjectIdByHostname(productName)
        if error:
            if productId == ['ItemNotFound', ['item']]:
                raise RuntimeError("Project with short name %r not found" %
                        (productName,))
            raise RuntimeError(*productId)

        if not buildName:
            buildName = productName

        error, buildId = self.server.newBuildWithOptions(productId, buildName,
                                            groupName,groupVersion.freeze(),
                                            groupFlavor.freeze(),
                                            buildType, options)
        if error:
            raise RuntimeError(*buildId)
        return buildId

    def startImage(self, buildId):
        error, result = self.server.startImageJob(buildId)
        if error:
            raise RuntimeError(*result)


    def getBuildFilenames(self, buildId):
        error, result = self.server.getBuildFilenames(self, buildId)
        if error:
            raise RuntimeError(*result)
        urls = []
        for fileDict in result:
            for urlId, urlType, url in fileDict['urls']:
                urls.append(url)
        return urls
