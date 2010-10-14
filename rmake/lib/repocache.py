#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

"""
Cache of changesets.
"""
from StringIO import StringIO
import os
import itertools

from conary import trove

from conary import files as cny_files
from conary.deps import deps
from conary.lib import digestlib
from conary.lib import sha1helper
from conary.lib import util
from conary.repository import changeset
from conary.repository import datastore
from conary.repository import errors
from conary.repository import filecontents


class CachingTroveSource:
    def __init__(self, troveSource, cacheDir, readOnly=False, depsOnly=False):
        self._troveSource = troveSource
        util.mkdirChain(cacheDir)
        self._depsOnly = depsOnly
        self._cache = RepositoryCache(cacheDir, readOnly=readOnly)

    def __getattr__(self, key):
        return getattr(self._troveSource, key)

    def getTroves(self, troveList, withFiles=True, callback = None):
        if self._depsOnly:
            return self._troveSource.getTroves(troveList, withFiles=withFiles,
                                               callback=callback)
        return self._cache.getTroves(self._troveSource, troveList,
                                     withFiles=withFiles, callback = None)

    def hasTroves(self, troveList):
        if self._depsOnly:
            return self._troveSource.hasTroves(troveList)
        return self._cache.hasTroves(self._troveSource, troveList)

    def hasTrove(self, name, version, flavor):
        return self.hasTroves([(name, version, flavor)])[name, version, flavor]

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
        if self._depsOnly:
            return self._troveSource.getFileContents(fileList,
                                                     callback=callback)
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
    batchSize = 20

    def __init__(self, cacheDir, readOnly=False, depsOnly=False):
        self.root = cacheDir
        self.store = DataStore(cacheDir)
        self.readOnly = readOnly
        self.depsOnly = depsOnly
        self.fileCache = LazyFileCache(100)

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

    def hashTroveList(self, nvfList, withFiles, withFileContents):
        ctx = digestlib.sha1()
        ctx.update('%s %s\n\n' % (withFiles, withFileContents))
        for name, version, flavor in nvfList:
            ctx.update('%s\n%s\n%s\n\n' % (name, version, flavor))
        return ctx.hexdigest()

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

    def hasTroves(self, repos, troveList):
        results = {}
        needed = []
        for troveTup in troveList:
            n,v,f = troveTup
            csHash = str(self.hashTrove(n,v,f,
                                        withFiles=False,
                                        withFileContents=False))
            if self.store.hasFile(csHash):
                results[troveTup] = True
            else:
                csHash = str(self.hashTrove(n,v,f,
                                        withFiles=True,
                                        withFileContents=False))
                if self.store.hasFile(csHash):
                    results[troveTup] = True
                else:
                    needed.append(troveTup)
        hasTroves = repos.hasTroves(needed)
        results.update(hasTroves)
        return results

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
        completed = 0
        while needed:
            if callback:
                callback.setChangesetHunk(completed + 1, total)
            batch, needed = needed[:self.batchSize], needed[self.batchSize:]

            # Grab a handful of troves at once.
            batchJob = [x[0] for x in batch]
            batchSet = repos.createChangeSet(batchJob,
                    recurse=False, callback=callback, withFiles=withFiles,
                    withFileContents=withFileContents)

            # Break the batch into individual troves and cache those.
            splitSets = splitChangeSet(batchJob, batchSet, withFiles,
                    withFileContents)
            for (job, csHash, csIndex), oneSet in zip(batch, splitSets):
                if self.readOnly:
                    changesets[csIndex] = oneSet
                    continue

                hashPath = self.store.hashToPath(csHash)
                self.store.makeDir(hashPath)

                fobj = util.AtomicFile(hashPath)
                oneSet.appendToFile(fobj)
                fobj.commit()

                # we could use this changeset, but 
                # cs.reset() is not necessarily reliable,
                # so instead we re-read from disk
                outFile = self.fileCache.open(self.store.hashToPath(csHash))
                changesets[csIndex] = changeset.ChangeSetFromFile(outFile)

            completed += len(batch)

        if callback:
            callback.setChangesetHunk(total, total)

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
        # nothing else will ensure this operation is atomic.
        assert(os.path.dirname(path) == os.path.dirname(tmpPath))
        os.rename(tmpPath, path)

class CacheError(Exception):
    pass

class LazyFileCache(util.LazyFileCache):
    # derive from util LazyFileCache which tries to read /proc/self/fd 
    # to get the total number of open files.  Unfortunately, when you 
    # drop privileges as a part of starting the daemon you lose the ability
    # to read /proc/self/fd

    def _getFdCount(self):
        return len([ x for x in self._fdMap.values() if x._realFd is not None])


def splitChangeSet(jobList, changeSet, withFiles=True, withFileContents=True):
    """Return a list of separate changesets for each job in C{jobList}."""
    out = []
    for name, (oldV, oldF), (newV, newF), absolute in jobList:
        assert oldV is oldF is None
        troveCs = changeSet.getNewTroveVersion(name, newV, newF)
        oneSet = changeset.ChangeSet()
        oneSet.newTrove(troveCs)
        if withFiles or withFileContents:
            _copyFiles(troveCs, changeSet, oneSet, withFiles, withFileContents)
        out.append(oneSet)
    return out


def _copyFiles(troveCs, fromSet, toSet, withFiles, withFileContents):
    for pathId, path, fileId, fileVer in sorted(troveCs.getNewFileList()):
        fileStream = fromSet.getFileChange(None, fileId)
        if withFiles:
            toSet.files.update(fromSet.files)
            #toSet.addFile(None, fileId, fileStream)
        if withFileContents:
            if not cny_files.frozenFileHasContents(fileStream):
                # Not a regular file, so no contents.
                continue
            flags = cny_files.frozenFileFlags(fileStream)
            if flags.isEncapsulatedContent() and not flags.isCapsuleOverride():
                # Encapsulated files also have no contents in the changeset.
                continue
            isConfig = flags.isConfig()
            tag, contents = fromSet.getFileContents(pathId, fileId,
                    compressed=isConfig)
            toSet.addFileContents(pathId, fileId, tag, contents,
                    cfgFile=isConfig, compressed=isConfig)
    fromSet.reset()
