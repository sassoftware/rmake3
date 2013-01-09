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


import sys


def decorator(decorator_func):
    """
    Write simple decorators by using this function as a decorator.
    
    The function decorated by this one, hereafter referred to as the decorator,
    will be invoked with the decorated function as the first argument and all
    positional and keyword arguments from the invocation of that function
    following it. The decorator should at some point probably invoke that
    function using the arguments supplied, possibly after modifying them.

    Example:
    >>> @decorator
    ... def addTwo(func, a):
    ...     b = 2
    ...     return func(a, b)
    ...
    >>> @addTwo
    ... def thingy(a, b):
    ...     print a, b
    ...
    >>> thingy(1)
    1 2
    """
    def decorateIt(decorated_func):
        def wrapper(*args, **kwargs):
            return decorator_func(decorated_func, *args, **kwargs)
        wrapper.func_name = decorated_func.func_name
        wrapper.func_wrapped = decorated_func
        return wrapper
    decorateIt.func_name = decorator_func.func_name
    decorateIt.func_wrapped = decorator_func
    return decorateIt


def getOrigin(depth=2):
    """
    Return a string describing which file and line invoked the calling
    function. Specifying a value higher than 2 for C{depth} will look that much
    further up the stack.
    """
    #pylint: disable-msg=W0212
    frame = sys._getframe(depth)
    return '%s:%d' % (frame.f_code.co_filename, frame.f_lineno)
