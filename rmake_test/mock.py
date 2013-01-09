#!/usr/bin/python2.4
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
Mock object implementation.

This mock object implementation is meant to be very forgiving - it returns a
new child Mock Object for every attribute accessed, and a mock object is
returned from every method call.

It is the tester's job to enabled the calls that they are interested in
testing, all calls where the return value of the call and side effects are not
recorded (logging, for example) are likely to succeed w/o effort.

If you wish to call the actual implementation of a function on a MockObject,
you have to enable it using enableMethod.  If you wish to use an actual
variable setting, you need to set it.

All enabling/checking methods for a MockObject are done through the _mock
attribute.  Example:

class Foo(object):
    def __init__(self):
        # NOTE: this initialization is not called by default with the mock
        # object.
        self.one = 'a'
        self.two = 'b'

    def method(self, param):
        # this method is enabled by calling _mock.enableMethod
        param.bar('print some data')
        self.printMe('some other data', self.one)
        return self.two

    def printMe(self, otherParam):
        # this method is not enabled and so is stubbed out in the MockInstance.
        print otherParam

def test():
    m = MockInstance(Foo)
    m._mock.set(two=123)
    m._mock.enableMethod('method')
    param = MockObject()
    rv = m.method(param)
    assert(rv == 123) #m.two is returned
    # note that param.bar is created on the fly as it is accessed, and 
    # stores how it was called.
    assert(param.bar._mock.assertCalled('print some data')
    # m.one and m.printMe were created on the fly as well
    # m.printMe remembers how it was called.
    m.printMe._mock.assertCalled('some other data', m.one)
    # attribute values are generated on the fly but are retained between
    # accesses.
    assert(m.foo is m.foo)

TODO: set the return values for particular function calls w/ particular
parameters.
"""
import new
import sys

_mocked = []

class MockObject(object):
    """
        Base mock object.

        Creates attributes on the fly, affect attribute values by using
        the _mock attribute, which is a MockManager.

        Initial attributes can be assigned by key/value pairs passed in.
    """
    #pylint: disable-msg=R0902

    def __init__(self, **kw):
        stableReturnValues = kw.pop('stableReturnValues', True)
        self._mock = MockManager(self, stableReturnValues=stableReturnValues)
        self.__dict__.update(kw)
        self._mock._dict = {}

    def __getattribute__(self, key):
        if key == '_mock' or self._mock.enabled(key):
            return object.__getattribute__(self, key)
        if key in self.__dict__:
            return self.__dict__[key]
        m = self._mock.getCalled(key)
        self.__dict__[key] = m
        return m

    def __setattr__(self, key, value):
        if key == '_mock' or self._mock.enabled(key):
            object.__setattr__(self, key, value)
        else:
            m = self._mock.setCalled(key, value)
            if not hasattr(self, key):
                object.__setattr__(self, key, m)

    def __setitem__(self, key, value):
        m = self._mock.setItemCalled(key, value)
        self._mock._dict[key] = m

    def __len__(self):
        if self._mock._dict:
            return len(self._mock._dict)
        return 1

    def __deepcopy__(self, _):
        return self

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    def __getitem__(self, key):
        if key in self._mock._dict:
            return self._mock._dict[key]
        else:
            m = self._mock.getItemCalled(key)
            self._mock._dict[key] = m
            return m

    def __hasattr__(self, key):
        if key == '_mock' or self._mock.enabled(key):
            return object.__hasattr__(self, key)
        return True

    def __call__(self, *args, **kw):
        return self._mock.called(args, kw)

class MockManager(object):
    #pylint: disable-msg=R0902
    noReturnValue = object()

    def __init__(self, obj, stableReturnValues=False):
        self._enabledByDefault = False
        self._enabled = set(['__dict__', '__methods__', '__class__',
                             '__members__', '__deepcopy__'])
        self._disabled = set([])
        self._errorToRaise = None
        self.calls = []
        self.callReturns = []
        self.getCalls = []
        self.setCalls = []
        self.getItemCalls = []
        self.setItemCalls = []
        self.hasCalls = []
        self.eqCalls = []
        self.obj = obj
        self.method = None
        self.origValue = None
        self.superClass = object
        self.stableReturnValues = stableReturnValues
        self.returnValues = self.noReturnValue

    def enableByDefault(self):
        self._enabledByDefault = True

    def disableByDefault(self):
        self._enabledByDefault = False

    def setDefaultReturn(self, returnValue):
        self.returnValues = [returnValue]

    def setReturn(self, returnValue, *args, **kw):
        self.clearReturn(*args, **kw)
        self.appendReturn(returnValue, *args, **kw)

    def appendReturn(self, returnValue, *args, **kw):
        kw = tuple(sorted(kw.items()))
        self.callReturns.append((args, kw, returnValue))

    def setReturns(self, returnValues, *args, **kw):
        self.clearReturn(*args, **kw)
        for rv in returnValues:
            self.appendReturn(rv, *args, **kw)

    def setDefaultReturns(self, returnValues):
        self.returnValues = returnValues

    def clearReturn(self, *args, **kw):
        kw = tuple(sorted(kw.items()))
        self.callReturns = [ x for x in self.callReturns
                             if (x[0], x[1]) != (args, kw) ]

    def setList(self, listItems):
        for idx, item in enumerate(listItems):
            self._dict[idx] = item


    def enableMethod(self, name):
        """
            Enables a method to be called from the given superclass.

            The function underlying the method is slurped up and assigned to 
            this class.
        """
        self.enable(name)
        func = getattr(self.superClass, name).im_func
        method = new.instancemethod(func, self.obj, self.obj.__class__)
        object.__setattr__(self.obj, name, method)

    def enable(self, *names):
        self._enabled.update(names)
        self._disabled.difference_update(names)

    def disable(self, *names):
        self._enabled.difference_update(names)
        self._disabled.update(names)
        for name in names:
            object.__setattr__(self.obj, name, MockObject())

    def enabled(self, name):
        if self._enabledByDefault:
            return name not in self._disabled
        else:
            return name in self._enabled

    def set(self, **kw):
        for key, value in kw.iteritems():
            self._enabled.add(key)
            setattr(self.obj, key, value)

    def raiseErrorOnAccess(self, error):
        self._errorToRaise = error

    def assertCalled(self, *args, **kw):
        kw = tuple(sorted(kw.items()))
        assert((args, kw) in self.calls)
        self.calls.remove((args, kw))

    def assertNotCalled(self):
        assert(not self.calls)

    def setCalled(self, key, value):
        if self._errorToRaise:
            self._raiseError()
        m = MockObject()
        self.setCalls.append((key, value, m))
        return m

    def setItemCalled(self, key, value):
        if self._errorToRaise:
            self._raiseError()
        m = MockObject()
        self.setItemCalls.append((key, value, m))
        return m

    def _raiseError(self):
        # idetifier err used to raise an exception is assigned to None
        #pylint: disable-msg=W0706
        err = self._errorToRaise
        self._errorToRaise = None
        raise err

    def getCalled(self, key):
        if self._errorToRaise:
            self._raiseError()
        if key in self.__class__.__dict__:
            raise RuntimeError('accessing method %r also defined in mock'
                ' object - prepend _mock to access, or enable attribute' % key)
        m = MockObject(stableReturnValues=self.stableReturnValues)
        self.getCalls.append((key, m))
        return m

    def getItemCalled(self, key):
        if self._errorToRaise:
            self._raiseError()
        m = MockObject(stableReturnValues=self.stableReturnValues)
        self.getItemCalls.append((key, m))
        return m


    def called(self, args, kw):
        kw = tuple(sorted(kw.items()))
        self.calls.append((args, kw))
        if self._errorToRaise:
            self._raiseError()
        else:
            rv = [x for x in self.callReturns if (x[0], x[1]) == (args, kw)]
            if rv:
                if len(rv) > 1:
                    self.callReturns.remove(rv[0])
                return rv[0][2]
            rv = [x[2] for x in self.callReturns
                  if not x[0] and x[1] == (('_mockAll', True),)]
            if rv:
                return rv[-1]
            else:
                if self.returnValues is not self.noReturnValue:
                    returnValue = self.returnValues[0]
                    if len(self.returnValues) > 1:
                        self.returnValues = self.returnValues[1:]
                    return returnValue
                if self.stableReturnValues:
                    self.returnValues = [MockObject(stableReturnValues=True)]
                    return self.returnValues[0]
                return MockObject()


    def popCall(self):
        call =  self.calls[0]
        self.calls = self.calls[1:]
        return call

class MockInstance(MockObject):

    def __init__(self, superClass, **kw):
        MockObject.__init__(self, **kw)
        self._mock.superClass = superClass

def attach(obj):
    if hasattr(obj, '__setattr__'):
        oldsetattr = obj.__setattr__
    if hasattr(obj, '__getattribute__'):
        oldgetattr = obj.__getattribute__

    def setattribute(self, key, value):
        if not isinstance(getattr(self, key), mock.MockObject()):
            oldsetattr(key, value)

    def getattribute(self, key):
        if not hasattr(self, key):
            oldsetattr(key, mock.MockObject())
        return oldgetattr(key)
    oldsetattr('__setattr__', new.instancemethod(setattribute, obj,
                                                 obj.__class__))
    oldsetattr('__getattribute__', new.instancemethod(getattribute,
                                                      obj, obj.__class__))

_NO_RETURN_VALUE = object()

def mockMethod(method, returnValue=_NO_RETURN_VALUE):
    self = method.im_self
    name = method.__name__
    origMethod = getattr(self, name)
    newMethod = MockObject()
    setattr(self, name, newMethod)
    newMethod._mock.method = origMethod
    newMethod._mock.origValue = origMethod
    if returnValue is not _NO_RETURN_VALUE:
        newMethod._mock.setDefaultReturn(returnValue)
    _mocked.append((self, name))
    return getattr(self, name)

def mockFunction(function, returnValue=_NO_RETURN_VALUE):
    module = sys.modules[function.func_globals['__name__']]
    name = function.func_name
    origFunction = getattr(module, name)
    newFunction = MockObject()
    setattr(module, name, newFunction)
    newFunction._mock.origValue = origFunction
    if returnValue is not _NO_RETURN_VALUE:
        newFunction._mock.setDefaultReturn(returnValue)
    _mocked.append((module, name))
    return getattr(module, name)

def mock(obj, attr, returnValue=_NO_RETURN_VALUE):
    m = MockObject()
    if hasattr(obj, attr):
        m._mock.origValue = getattr(obj, attr)
    setattr(obj, attr, m)
    if returnValue is not _NO_RETURN_VALUE:
        m._mock.setDefaultReturn(returnValue)
    _mocked.append((obj, attr))

def unmockAll():
    for obj, attr in _mocked:
        if not hasattr(getattr(obj, attr), '_mock'):
            continue
        setattr(obj, attr, getattr(obj, attr)._mock.origValue)
    _mocked[:] = []

def mockClass(class_, *args, **kw):
    commands = []
    runInit = kw.pop('mock_runInit', False)
    for k, v in kw.items():
        if k.startswith('mock_'):
            if not isinstance(v, (list, tuple)):
                v = [v]
            commands.append((k[5:], v))
            kw.pop(k)
    class _MockClass(MockInstance, class_):
        def __init__(self, *a, **k):
            MockInstance.__init__(self, class_, *args, **kw)
            if runInit:
                self._mock.enableByDefault()
                class_.__init__(self, *a, **k)
            self._mock.called(a, k)
            for command, params in commands:
                getattr(self._mock, command)(*params)

    return _MockClass

def mockFunctionOnce(obj, attr, returnValue):
    newFn = lambda *args, **kw: returnValue
    return replaceFunctionOnce(obj, attr, newFn)

def replaceFunctionOnce(obj, attr, newFn):
    # Unused variable func_name - huh?
    #pylint: disable-msg=W0612
    curValue = getattr(obj, attr)
    def restore():
        setattr(obj, attr, curValue)

    def fun(*args, **kw):
        restore()
        return newFn(*args, **kw)
    setattr(obj, attr, fun)
    fun.func_name = attr
    fun.restore = restore
