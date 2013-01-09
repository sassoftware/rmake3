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
