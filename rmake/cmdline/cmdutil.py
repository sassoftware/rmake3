#
# Copyright (c) 2007 rPath, Inc.  All Rights Reserved.
#
"""
Command line utilities.  Should never be needed outside of the command line parsing, and thus should never need to be imported by anyone.
"""
import re

from conary.conaryclient import cmdline

def parseTroveSpec(troveSpec, allowEmptyName=False):
    troveSpec, context = re.match('^(.*?)(?:{(.*)})?$', troveSpec).groups()
    troveSpec = cmdline.parseTroveSpec(troveSpec, allowEmptyName=allowEmptyName)
    return troveSpec + (context,)

def parseTroveSpecContext(troveSpec, allowEmptyName=False):
    troveSpec, context = re.match('^(.*?)(?:{(.*)})?$', troveSpec).groups()
    return troveSpec, context

def getSpecStringFromTuple(spec):
    troveSpec = ''
    if len(spec) == 4:
        context = spec[3]
    else:
        context = None
    if spec[0] is not None:
        troveSpec = spec[0]
    if spec[1] is not None:
        troveSpec += '=%s' % spec[1]
    if spec[2] is not None:
        troveSpec += '[%s]' % spec[2]
    return troveSpec, context

