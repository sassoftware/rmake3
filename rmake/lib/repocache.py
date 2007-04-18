#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
"""
Cache of changesets.
"""
from StringIO import StringIO
import errno
import os
import itertools
import tempfile

from conary import trove

from conary.deps import deps
from conary.lib import sha1helper
from conary.lib import util
from conary.repository import changeset
from conary.repository import datastore
from conary.repository import errors
from conary.repository import filecontents
from conary.repository import trovesource

class CachingTroveSource:
    def __init__(self, troveSource, cacheDir, readOnly=False):
        self._troveSource = troveSource
        util.mkdirChain(cacheDir)
        self._cache = RepositoryCache(cacheDir, readOnly=readOnly)

    def __getattr__(self, key):
        return getattr(self._troveSource, key)

    def getTroves(self, troveList, withFiles=True, callback = None):
        return self._cache.getTroves(self._troveSource, troveList,
                                     withFiles=withFiles, callback = None)

    def getTrove(self, name, version, flavor, withFiles=True, callback=None):
        trv = self.getTroves([(name, version, flavor)], withFiles=withFiles,
                              callback=callback)[0]
        if trv is None:
            raise errors.TroveMissing(name, version)
        return trv

    def resolveDependenciesByGroups(self, groupTroves, depList):
        if not (groupTroves and depList):
            return {}
        return self._cache.resolveDependenciesByGroups(self._troveSource, 
                                                       groupTroves,
                                                       depList)

    def getFileContents(self, fileList, callback = None):
        return self._cache.getFileContents(self._troveSource,
                                           fileList, callback=callback)

class DependencyResultList(trove.TroveTupleList):
    def get(self):
        rv = [ (x.name(), x.version().copy(), x.flavor()) for x in self.iter() ]
        [ x[1].resetTimeStamps() for x in rv ]
        return rv


class RepositoryCache(object):
    """
        We cache changeset files by component.  When conary is fixed, we'll
        be able to combine the download of these troves.
    """
    def __init__(self, cacheDir, readOnly=False):
        self.root = cacheDir
        self.store = DataStore(cacheDir)
        self.readOnly = readOnly
        self.fileCache = util.LazyFileCache()

    def hashGroupDeps(self, groupTroves, depClass, dependency):
        depSet = deps.DependencySet()
        depSet.addDep(depClass, dependency)
        frz = depSet.freeze()
        troveList = sorted(self.hashTrove(withFiles=False,
                                          withFileContents=False,
                                          *x.getNameVersionFlavor())
                           for x in groupTroves)
        str = '[1]%s%s%s' % (len(frz), frz, ''.join(troveList))
        return sha1helper.sha1ToString(sha1helper.sha1String(str))

    def hashFile(self, fileId, fileVersion):
        # we add extra delimiters here because we can be sure they they
        # will result in a unique string for each n,v,f
        return sha1helper.sha1ToString(
                    sha1helper.sha1String('[0]%s=%s' % (fileId, fileVersion)))

    def hashTrove(self, name, version, flavor, withFiles, withFileContents):
        # we add extra delimiters here because we can be sure they they
        # will result in a unique string for each n,v,f
        return sha1helper.sha1ToString(
                sha1helper.sha1String('%s=%s[%s]%s%s' % (name, version, flavor, withFiles, withFileContents)))

    def getChangeSetsForTroves(self, repos, troveList, withFiles=True,
                               withFileContents=True, callback=None):
        return self.getChangeSets(repos,
                                  [(x[0], (None, None), (x[1], x[2]), False) 
                                   for x in troveList ],
                                   withFiles, withFileContents,
                                   callback=callback)


    def getTroves(self, repos, troveList, withFiles=True,
                  withFileContents=False, callback=None):
        csList = self.getChangeSetsForTroves(repos, troveList, withFiles,
                                             withFileContents, callback)
        l = []
        for cs, info in itertools.izip(csList, troveList):
            if cs is None:
                l.append(None)
                continue
            troveCs = cs.getNewTroveVersion(*info)
            # trove integrity checks don't work when file information is
            # excluded
            t = trove.Trove(troveCs, skipIntegrityChecks = not withFiles)
            l.append(t)
        return l

    def resolveDependenciesByGroups(self, repos, groupTroves, depList):
        allToFind = []
        allFound = []
        allMissing = []
        for depSet in depList:
            d = {}
            toFind = deps.DependencySet()
            found  = []
            missingIdx = []
            allToFind.append(toFind)
            allFound.append(found)
            allMissing.append(missingIdx)
            for idx, (depClass, dependency) in enumerate(depSet.iterDeps(sort=True)):
                depHash = str(self.hashGroupDeps(groupTroves, depClass, 
                                                 dependency))
                if self.store.hasFile(depHash):
                    outFile = self.store.openFile(depHash)
                    results = DependencyResultList(outFile.read()).get()
                    found.append(results)
                else:
                    toFind.addDep(depClass, dependency)
                    found.append(None)
                    missingIdx.append((idx, depHash))
        if [ x for x in allToFind if x]:
            allResults = repos.resolveDependenciesByGroups(groupTroves,
                                                           allToFind)
            for found, toFind, missingIdx in itertools.izip(allFound,
                                                            allToFind,
                                                            allMissing):
                if toFind.isEmpty():
                    continue
                iter = itertools.izip(missingIdx, toFind.iterDeps(sort=True), 
                                      allResults[toFind])
                for (idx, depHash), (depClass, dependency), resultList in iter:
                    found[idx] = resultList
                    if self.readOnly:
                        continue
                    depResultList = DependencyResultList()
                    [ depResultList.add(*x) for x in resultList ]
                    s = StringIO()
                    s.write(depResultList.freeze())
                    s.seek(0)
                    self.store.addFile(s, depHash, integrityCheck=False)
        allResults = {}
        for result, depSet in itertools.izip(allFound, depList):
            allResults[depSet] = result
        return allResults

    def getChangeSets(self, repos, jobList, withFiles=True,
                      withFileContents=True, callback=None):
        for job in jobList:
            if job[1][0]:
                raise CacheError('can only cache install,'
                                 ' not update changesets')
            if job[3]:
                raise CacheError('Cannot cache absolute changesets')

        changesets = [None for x in jobList]
        needed = []
        for idx, job in enumerate(jobList):
            csHash = str(self.hashTrove(job[0], job[2][0], job[2][1],
                                        withFiles, withFileContents))
            if self.store.hasFile(csHash):
                outFile = self.fileCache.open(self.store.hashToPath(csHash))
                #outFile = self.store.openRawFile(csHash)
                changesets[idx] = changeset.ChangeSetFromFile(outFile)
            else:
                needed.append((job, csHash, idx))


        total = len(needed)
        for idx, (job, csHash, csIndex) in enumerate(needed):
            if callback:
                callback.setChangesetHunk(idx + 1, total)

            cs = repos.createChangeSet([job], recurse=False,
                                       callback=callback, withFiles=withFiles,
                                       withFileContents=withFileContents)
            if self.readOnly:
                changesets[csIndex] = cs
                continue

            tmpFd, tmpName = tempfile.mkstemp()
            os.close(tmpFd)
            cs.writeToFile(tmpName)
            del cs
            # we could use this changeset, but 
            # cs.reset() is not necessarily reliable,
            # so instead we re-read from disk
            self.store.addFileFromTemp(csHash, tmpName)

            outFile = self.fileCache.open(self.store.hashToPath(csHash))
            #outFile = self.store.openRawFile(csHash)
            changesets[csIndex] = changeset.ChangeSetFromFile(outFile)

        return changesets

    def getFileContents(self, repos, fileList, callback=None):
        contents = []
        needed = []
        for idx, item in enumerate(fileList):
            fileId, fileVersion = item[0:2]

            fileHash = str(self.hashFile(fileId, fileVersion))
            if self.store.hasFile(fileHash):
                f = self.store.openFile(fileHash)
                content = filecontents.FromFile(f)
                contents.append(content)
            else:
                contents.append(None)
                needed.append((idx, (fileId, fileVersion), fileHash))

        total = len(needed)
        newContents = repos.getFileContents([x[1] for x in needed],
                                            callback=callback)
        itemList = itertools.izip(newContents, needed)
        for content, (idx, (fileId, fileVersion), fileHash) in itemList:
            if not self.readOnly:
                self.store.addFile(content.get(), fileHash,
                                   integrityCheck=False)
            contents[idx] = content

        return contents

    def getFileContentsPaths(self, repos, fileList, callback=None):
        self.getFileContents(repos, fileList, callback=None)
        paths = []
        for idx, item in enumerate(fileList):
            fileId, fileVersion = item[0:2]
            fileHash = str(self.hashFile(fileId, fileVersion))
            paths.append(self.store.hashToPath(fileHash))
        return paths

class DataStore(datastore.DataStore):
    def addFileFromTemp(self, hash, tmpPath):
        """
            Method to insert data into a datastore from a temporary file.
            The file is renamed to be in the datastore.
        """
        path = self.hashToPath(hash)
        self.makeDir(path)
        if os.path.exists(path): return

        try:
            util.rename(tmpPath, path)
        except OSError, err:
            if err.errno != errno.EXDEV:
                raise
            else:
                util.copyfile(tmpPath, path)
                util.removeIfExists(tmpPath)

class CacheError(Exception):
    pass

