import urlparse
import xmlrpclib
from M2Crypto import m2xmlrpclib

class RbuilderClient(object):
    def __init__(self, rbuilderUrl, user, pw):
        scheme, netloc, path, query, fragment = urlparse.urlsplit(rbuilderUrl)
        path = 'xmlrpc-private'
        netloc = netloc.split('@', 1)[-1]
        netloc = '%s:%s@' % (user, pw) + netloc
        rbuilderUrl =  urlparse.urlunsplit(
                                (scheme, netloc, path, query, fragment))

        if scheme == 'https':
            self.server = m2xmlrpclib.ServerProxy(rbuilderUrl)
        else:
            self.server = xmlrpclib.ServerProxy(rbuilderUrl)

    def getBuild(self, buildId):
        error, result = self.server.getBuild(buildId)
        if error:
            raise RuntimError(*productId)
        return result

    def newBuildWithOptions(self, productName, groupName, groupVersion,
                            groupFlavor, buildType, options):
        error, productId = self.server.getProjectIdByHostname(productName)
        if error:
            raise RuntimeError(*productId)

        error, buildId = self.server.newBuildWithOptions(productId, productName,
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
            

