#
# Copyright (c) 2007 rPath, Inc.  All Rights Reserved.
#
"""
Command line utilities.  Should never be needed outside of the command line parsing, and thus should never need to be imported by anyone.
"""
import re

from conary.conaryclient import cmdline

def parseTroveSpec(troveSpec):
    troveSpec, context = re.match('^(.*?)(?:{(.*)})?$', troveSpec).groups()
    troveSpec = cmdline.parseTroveSpec(troveSpec)
    return troveSpec + (context,)
