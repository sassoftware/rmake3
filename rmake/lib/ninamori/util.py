#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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
