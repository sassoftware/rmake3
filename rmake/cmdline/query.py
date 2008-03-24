#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#
import fcntl
import itertools
import struct
import sys
import termios
import textwrap
import time

from conary.deps import deps

from rmake.cmdline import cmdutil
from rmake.build import buildtrove
from rmake.lib import flavorutil

def getTerminalSize(out=None):
    if out is None:
        out = sys.stdout.fileno()
    elif not isinstance(out, int):
        out = out.fileno()

    s = struct.pack("HHHH", 0, 0, 0, 0)
    try:
        lines, cols = struct.unpack("HHHH", fcntl.ioctl(out,
                                    termios.TIOCGWINSZ, s))[:2]
    except IOError:
        return 25, 80
    return lines, cols

class DisplayConfig(object):
    def __init__(self, client, displayTroves=False, displayJobs=True,
                 displayJobDetail=False, displayTroveDetail=False,
                 showLogs=False, showBuildLogs=False, showFullVersions=False,
                 showFullFlavors=False, showLabels=False,
                 showTracebacks=False, showConfig=False):
        self.client = client
        self.displayTroves = displayTroves
        self.displayJobs = displayJobs
        self.displayJobDetail = displayJobDetail
        self.displayTroveDetail = displayTroveDetail
        self.showLogs = showLogs
        self.showBuildLogs = showBuildLogs
        self.showFullVersions = showFullVersions
        self.showFullFlavors = showFullFlavors
        self.showLabels = showLabels
        self.showTracebacks = showTracebacks
        self.showConfig = showConfig

        self.needTroves = displayTroves or displayJobDetail or showBuildLogs

    def getClient(self):
        return self.client

def getTimeDifference(totalSeconds):
    if not totalSeconds:
        return '0 secs'
    seconds = totalSeconds % 60
    minutes = int(totalSeconds / 60)
    hours = int(minutes / 60)
    minutes = minutes % 60
    total = []
    if hours:
        total.append('%d hour%s' % (hours, hours > 1 and 's' or ''))
    if minutes:
        total.append('%d min%s' % (minutes, minutes > 1 and 's' or ''))
    if seconds and not hours:
        total.append('%d sec%s' % (seconds, seconds > 1 and 's' or ''))
    return ', '.join(total)

def getJobsToDisplay(dcfg, client, jobId=None, troveSpecs=None,
                     activeOnly=False, jobLimit=None):
    if troveSpecs:
        troveSpecs = ( cmdutil.parseTroveSpec(x) for x in troveSpecs )
        troveSpecs = [ (x[0].split(':')[0] + ':source', x[1], x[2], x[3]) for x in troveSpecs ]

    # Only retrieve the configuration if we have to show it
    withConfigs = dcfg.showConfig
    if not jobId:
        jobIds = client.client.listJobs(activeOnly=activeOnly,
                                        jobLimit=jobLimit)
        jobList = client.client.getJobs(jobIds,
                                        withTroves=dcfg.needTroves)
    else:
        jobList = [ client.client.getJob(jobId, withConfigs = withConfigs) ]

    newJobList = []
    if troveSpecs:
        for job in jobList:
            results = job.findTrovesWithContext(None, troveSpecs, None,
                                                allowMissing=True)
            allTups = list(itertools.chain(*results.itervalues()))
            if allTups:
                newJobList.append((job, allTups))
        return newJobList
    else:
        return [ (x, None) for x in jobList ]

def displayJobInfo(client, jobId=None, troveSpecs=[], displayTroves=False,
                   displayDetails=False, showLogs=False, showBuildLogs=False,
                   showFullVersions=False, showFullFlavors=False,
                   showLabels=False, showTracebacks=False,
                   showConfig=False, activeOnly=False, jobLimit=None,
                   out=sys.stdout):
    if troveSpecs:
        displayTroves = True

    displayJobDetail = False
    displayTroveDetail = False
    if displayDetails:
        displayJobDetail = True
        if displayTroves:
            displayTroveDetail = True
    if showTracebacks or showBuildLogs or showLogs:
        displayTroves = displayTroveDetail = True

    dcfg = DisplayConfig(client,
                         displayJobs=True,
                         displayJobDetail=displayJobDetail,
                         displayTroves=displayTroves,
                         displayTroveDetail=displayTroveDetail,
                         showConfig=showConfig,
                         showTracebacks=showTracebacks,
                         showLogs=showLogs,
                         showBuildLogs=showBuildLogs,
                         showFullVersions=showFullVersions,
                         showFullFlavors=showFullFlavors,
                         showLabels=showLabels)

    jobList = getJobsToDisplay(dcfg, client, jobId, troveSpecs,
                               jobLimit=jobLimit, activeOnly=activeOnly)
    for job, troveTupList in jobList:
        dcfg.flavorsByName = getFlavorSpecs(job)
        displayOneJob(dcfg, job, troveTupList, out)

def getOldTime(t):
    diff = int(time.time() - t)
    days = diff / (3600 * 24)
    if days > 14:
        return '%s weeks ago' % (days / 7)
    if days > 7:
        return '%s week ago' % (days / 7)
    elif days > 1:
        return '%s days ago' % (days)
    else:
        hours = (diff / 3600) % 24
        if days:
            return '1 day, %s hours ago' % hours
        elif hours:
            if hours == 1:
                return '1 hour ago'
            return '%s hours ago' % hours
        elif diff / 60 == 1:
            return '1 minute ago'
        elif diff / 60 == 0:
            return 'just now'
        return '%s minutes ago' % (diff / 60)

def displayOneJob(dcfg, job, troveTupList, out=sys.stdout):
    if dcfg.displayJobs:
        if dcfg.showConfig:
            configs = job.getConfigDict()
            if troveTupList:
                # Extract contexts for the troves in the job
                buildTroveList = [ job.troves[x] for x in troveTupList ]
                contexts = set(x.context for x in buildTroveList)
                for ctx in sorted(contexts):
                    if ctx:
                        out.write('\n\n[%s]\n' % ctx)
                    configs[ctx].display(out)
                return
            mainConfig = configs.pop('')
            mainConfig.setDisplayOptions(showContexts=True)
            for ctxName, config in configs.items():
                ncfg = config.__class__()
                for k, v in config.iteritems():
                    if k in mainConfig and mainConfig[k] != v:
                        ncfg.setValue(k, v)
                    else:
                        # We need to convince the config object not to display
                        # default values. Using the regular __setitem__ will
                        # set isDefault to False, so we do this instead.
                        ncfg.__dict__[k] = None
                mainConfig._addSection(ctxName, ncfg)
            mainConfig.display(out)
            return
        elif dcfg.displayJobDetail:
            displayJobDetail(dcfg, job, out)
        else:
            times = []
            if job.finish:
                timeStr = getOldTime(job.finish)
            elif job.start:
                timeStr = getOldTime(job.start)
            else:
                timeStr = ''
            out.write('%-5s %-25s %s\n' % (job.jobId, job.getStateName(), timeStr))

            if not troveTupList:
                troveList = sorted(job.iterTroveList())
                troveStr = ', '.join(x[0].split(':')[0] for x in troveList[:3])
                troveListLen = len(troveList)
                if troveListLen > 3:
                    troveStr += '...'
                out.write('%5s (%s troves) %s\n' % (' ', troveListLen, troveStr))

        if dcfg.showLogs:
            client = dcfg.getClient()
            for (timeStamp, message, args) in client.client.getJobLogs(job.jobId):
                out.write('[%s] %s\n' % (timeStamp, message))

    if dcfg.displayTroves:
        printTroves(dcfg, job, troveTupList, out)

def displayJobDetail(dcfg, job, out=sys.stdout):
    def write(txt=''):
        return out.write(txt + '\n')
    total   = len(list(job.iterTroves()))
    unbuilt  = len(list(job.iterUnbuiltTroves()))
    preparing = len(list(job.iterPreparingTroves()))
    building = len(list(job.iterBuildingTroves()))
    waiting = len(list(job.iterWaitingTroves()))
    built    = len(list(job.iterBuiltTroves()))
    failed   = len(list(job.iterFailedTroves()))

    write('%-4s   State:    %-20s' % (job.jobId, job.getStateName()))
    write('       Status:   %-20s' % job.status)
    if job.start:
        startTime = time.strftime('%x %X', time.localtime(job.start))
        if job.finish:
            totalTime = getTimeDifference(job.finish - job.start)
        elif job.isBuilding():
            totalTime = getTimeDifference(time.time() - job.start)
        else:
            totalTime = 'Never finished'
        write('       Started:  %-20s Build Time: %s' % (startTime, totalTime))
    write('       To Build: %-20s Building: %s' % (unbuilt, building + waiting + preparing))
    write('       Built:    %-20s Failed:   %s' % (built, failed))
    write()

def printTroves(dcfg, job, troveTupList, out=sys.stdout):
    if troveTupList or dcfg.displayTroveDetail:
        if troveTupList is None:
            troveTupList = job.iterTroveList(True)
        for troveTup in sorted(troveTupList):
            printOneTrove(dcfg, job, job.getTrove(*troveTup), out=out)
    else:
        displayTrovesByState(job, out=out)
    out.write("\n")

def getTroveSpec(dcfg, item):
    if len(item) == 3:
        name, version, flavor = item
        context = ''
    else:
        (name, version, flavor, context) = item
    if dcfg.showFullVersions:
        pass
    elif dcfg.showLabels:
        version = '%s/%s' % (version.trailingLabel(), 
                             version.trailingRevision())
    else:
        version = ':%s/%s' % (version.trailingLabel().branch, 
                              version.trailingRevision())

    if dcfg.showFullFlavors:
        flavor = '[%s]' % flavor
    else:
        flavor = dcfg.flavorsByName[name, flavor]
        if not flavor.isEmpty():
            flavor = '[%s]' % flavor
    if context:
        return '%s=%s%s{%s}' % (name, version, flavor, context)
    return '%s=%s%s' % (name, version, flavor)

def getFlavorSpecs(job):
    flavorsByName = {}
    for nvf in job.iterTroveList():
        flavorsByName.setdefault(nvf[0], []).append(nvf[2])
    for trove in job.iterTroves():
        if not trove:
            continue
        for nvf in trove.iterBuiltTroves():
            flavorsByName.setdefault(nvf[0], []).append(nvf[2])
    for name, flavorList in flavorsByName.items():
	allFlavors = []
        for flavor in flavorList:
            archFlags = flavorutil.getArchFlags(flavor, withFlags=False)
            flavorsByName[name, flavor] = archFlags
	if len(set(allFlavors)) != len(allFlavors):
            diffs = deps.flavorDifferences(flavorList)
            for flavor in flavorList:
                 archFlags = flavorsByName[name, flavor]
                 archFlags.union(diffs[flavor])
    return flavorsByName

def displayTrovesByState(job, indent='     ', out=sys.stdout):
    flavorsByName = getFlavorSpecs(job)

    for state in (buildtrove.TROVE_STATE_WAITING,
                   buildtrove.TROVE_STATE_RESOLVING,
                   buildtrove.TROVE_STATE_PREPARING,
                   buildtrove.TROVE_STATE_BUILDING,
                   buildtrove.TROVE_STATE_BUILDABLE,
                   buildtrove.TROVE_STATE_UNBUILDABLE,
                   buildtrove.TROVE_STATE_FAILED,
                   buildtrove.TROVE_STATE_BUILT,
                   buildtrove.TROVE_STATE_PREBUILT,
                   buildtrove.TROVE_STATE_INIT):
        troves = sorted(job.iterTrovesByState(state))
        if not troves:
            continue
        out.write('\n%s%s Troves [%s]:\n' % (indent,troves[0].getStateName(),
                                             len(troves)))
        txt = '  '.join('%s[%s]' % (x.getName().split(':')[0], flavorsByName[x.getName(), x.getFlavor()])  for x in troves)
        lines, cols = getTerminalSize(out)
        if not cols:
            cols = 80
        out.write(textwrap.fill(txt, initial_indent=indent, subsequent_indent=indent, width=max(cols - len(indent), 20)))
        out.write('\n\n')

def printOneTrove(dcfg, job, trove, indent='       ', out=sys.stdout):
    displayTroveDetail(dcfg, job, trove, indent, out)
    if dcfg.showLogs:
        client = dcfg.getClient()
        mark = 0
        while True:
            logs = client.client.getTroveLogs(job.jobId,
                                              trove.getNameVersionFlavor(True),
                                              mark)
            if not logs:
                break
            mark += len(logs)
            for (timeStamp, message, args) in logs:
                out.write('[%s] %s\n' % (timeStamp, message))

    if dcfg.showBuildLogs:
        showBuildLog(dcfg, job, trove, out)

def showBuildLog(dcfg, job, trove, out=sys.stdout):
    client = dcfg.getClient()

    mark = 0
    moreData, data, mark = client.client.getTroveBuildLog(job.jobId,
                                        trove.getNameVersionFlavor(True), mark)
    if not moreData and not data:
        out.write('No build log.')
        return

    out.write("")
    out.write(data,)

def displayTroveDetail(dcfg, job, trove, indent='     ', out=sys.stdout):
    def write(line=''):
        out.write(line + '\n')

    if not hasattr(dcfg, 'flavorsByName'):
        dcfg.flavorsByName = getFlavorSpecs(job)
    troveSpec = getTroveSpec(dcfg, trove.getNameVersionFlavor(withContext=True))
    write('%s%s' % (indent, troveSpec))
    write('%s  State: %-20s' % (indent, trove.getStateName()))
    if trove.start:
        startTime = time.strftime('%x %X', time.localtime(trove.start))
        if trove.finish:
            totalTime = getTimeDifference(trove.finish - trove.start)
        elif trove.isBuilding():
            totalTime = getTimeDifference(time.time() - trove.start)
        else:
            totalTime = 'Never finished'
        write('%s  Start: %-20s Build time: %-20s' % (indent,
                                                    startTime, totalTime))
    host = trove.getChrootHost()
    path = trove.getChrootPath()
    if host:
        if host == '_local_':
            host = ''
        else: 
            host += ':'
        write('%s  Build Path: %s%s' % (indent, host, path))
    if trove.status:
        write('%s  Status: %-20s' % (indent, trove.status))
    if trove.isFailed():
        failureReason = trove.getFailureReason()
        if dcfg.showTracebacks and failureReason.hasTraceback():
            write()
            write(failureReason.getTraceback())
            write()
            write()
    elif trove.isBuilt():
        write('%s  Built Troves:' % (indent,))
        for (n,v,f) in sorted(trove.iterBuiltTroves()):
            if ':' in n: continue
            write("%s    %s" % (indent, getTroveSpec(dcfg, (n, v, f))))

def listChroots(client, cfg, allChroots=False):
    chrootsByHost =  {}
    for chroot in client.client.listChroots():
        chrootsByHost.setdefault(chroot.host, []).append(chroot)
    for host in sorted(chrootsByHost):
        if host != '_local_':
            print '%s:' % host
        for chroot in chrootsByHost[host]:
            if chroot.active or allChroots:
                displayChroot(chroot)

def displayChroot(chroot):
    if chroot.active:
        active = ' (Building)'
    else:
        active = ' (Inactive)'
    name = '%s%s:' % (chroot.path, active)
    troveTuple = ''
    if chroot.jobId:
        jobId = '[%s]' % chroot.jobId
        if chroot.troveTuple:
            n,v,f = chroot.troveTuple
            arch = flavorutil.getArch(f)
            if arch:
                arch = '[is: %s]' % arch
            else:
                arch = None
            troveTuple = ' %s=%s/%s' % (n, v.trailingRevision(),
                                        arch)
        jobInfo = '%s%s' % (jobId, troveTuple)
    else:
        jobInfo = '[Unknown]'

    print '   %-18s %s' % (name, jobInfo)

