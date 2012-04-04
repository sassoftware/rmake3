#!/usr/bin/python
#
# Copyright (c) rPath, Inc.
#

import sys
from testrunner import suite
from rmake_test import resources


class Suite(suite.TestSuite):
    testsuite_module = sys.modules[__name__]
    topLevelStrip = 0

    def getCoverageDirs(self, handler, environ):
        return [
                resources.get_path('rmake'),
                resources.get_path('rmake_plugins'),
                ]

    def sortTests(self, tests):
        order = {'smoketest': 0, 
                 'unit_test' :1,
                 'functionaltest':2}
        maxNum = len(order)
        tests = [ (test, test.index('test')) for test in tests]
        tests = sorted((order.get(test[:index+4], maxNum), test)
                       for (test, index) in tests)
        tests = [ x[1] for x in tests if x[1].startswith('rmake_test') ]
        return tests


if __name__ == '__main__':
    Suite().run()
