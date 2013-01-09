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


"""
Backwards-compatible xmlrpclib implementation that uses only parsers tolerant
of null bytes and other binary garbage.
"""

import xmlrpclib

dumps = xmlrpclib.dumps


def getparser():
    target = xmlrpclib.Unmarshaller()
    if getattr(xmlrpclib, 'SgmlopParser', None):
        parser = xmlrpclib.SgmlopParser(target)
    else:
        parser = xmlrpclib.SlowParser(target)
    return parser, target


def loads(data):
    p, u = getparser()
    p.feed(data)
    p.close()
    return u.close(), u.getmethodname()
