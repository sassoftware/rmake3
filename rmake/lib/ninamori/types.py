#
# Copyright (c) 2009 rPath, Inc.
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

import itertools
import sys
from keyword import iskeyword as _iskeyword
from operator import itemgetter as _itemgetter


# shamelessly ripped from python 2.6
def namedtuple(typename, field_names, verbose=False):
    """Returns a new subclass of tuple with named fields.

    >>> Point = namedtuple('Point', 'x y')
    >>> Point.__doc__                   # docstring for the new class
    'Point(x, y)'
    >>> p = Point(11, y=22)             # instantiate with positional args or keywords
    >>> p[0] + p[1]                     # indexable like a plain tuple
    33
    >>> x, y = p                        # unpack like a regular tuple
    >>> x, y
    (11, 22)
    >>> p.x + p.y                       # fields also accessable by name
    33
    >>> d = p._asdict()                 # convert to a dictionary
    >>> d['x']
    11
    >>> Point(**d)                      # convert from a dictionary
    Point(x=11, y=22)
    >>> p._replace(x=100)               # _replace() is like str.replace() but targets named fields
    Point(x=100, y=22)

    """

    # Parse and validate the field names.  Validation serves two purposes,
    # generating informative error messages and preventing template injection attacks.
    if isinstance(field_names, basestring):
        field_names = field_names.replace(',', ' ').split() # names separated by whitespace and/or commas
    field_names = tuple(map(str, field_names))
    for name in (typename,) + field_names:
        if [c for c in name if not c.isalnum() and c != '_']:
            raise ValueError('Type names and field names can only contain alphanumeric characters and underscores: %r' % name)
        if _iskeyword(name):
            raise ValueError('Type names and field names cannot be a keyword: %r' % name)
        if name[0].isdigit():
            raise ValueError('Type names and field names cannot start with a number: %r' % name)
    seen_names = set()
    for name in field_names:
        if name.startswith('_'):
            raise ValueError('Field names cannot start with an underscore: %r' % name)
        if name in seen_names:
            raise ValueError('Encountered duplicate field name: %r' % name)
        seen_names.add(name)

    # Create and fill-in the class template
    numfields = len(field_names)
    argtxt = repr(field_names).replace("'", "")[1:-1]   # tuple repr without parens or quotes
    reprtxt = ', '.join('%s=%%r' % name for name in field_names)
    dicttxt = ', '.join('%r: t[%d]' % (name, pos) for pos, name in enumerate(field_names))
    template = '''class %(typename)s(tuple):
        '%(typename)s(%(argtxt)s)' \n
        __slots__ = () \n
        _fields = %(field_names)r \n
        def __new__(cls, %(argtxt)s):
            return tuple.__new__(cls, (%(argtxt)s)) \n
        @classmethod
        def _make(cls, iterable, new=tuple.__new__, len=len):
            'Make a new %(typename)s object from a sequence or iterable'
            result = new(cls, iterable)
            if len(result) != %(numfields)d:
                raise TypeError('Expected %(numfields)d arguments, got %%d' %% len(result))
            return result \n
        def __repr__(self):
            return '%(typename)s(%(reprtxt)s)' %% self \n
        def _asdict(t):
            'Return a new dict which maps field names to their values'
            return {%(dicttxt)s} \n
        def _replace(self, **kwds):
            'Return a new %(typename)s object replacing specified fields with new values'
            result = self._make(map(kwds.pop, %(field_names)r, self))
            if kwds:
                raise ValueError('Got unexpected field names: %%r' %% kwds.keys())
            return result \n
        def __getnewargs__(self):
            return tuple(self) \n\n''' % locals()
    for i, name in enumerate(field_names):
        template += '        %s = property(itemgetter(%d))\n' % (name, i)
    if verbose:
        print template

    # Execute the template string in a temporary namespace and
    # support tracing utilities by setting a value for frame.f_globals['__name__']
    namespace = dict(itemgetter=_itemgetter, __name__='namedtuple_%s' % typename)
    try:
        exec template in namespace
    except SyntaxError, e:
        raise SyntaxError(str(e) + ':\n' + template)
    result = namespace[typename]

    # For pickling to work, the __module__ variable needs to be set to the frame
    # where the named tuple is created.  Bypass this step in enviroments where
    # sys._getframe is not defined (Jython for example).
    if hasattr(sys, '_getframe'):
        result.__module__ = sys._getframe(1).f_globals.get('__name__', '__main__')

    return result


def constants(name, nameList, prefix=True):
    nameList = nameList.split()
    if prefix:
        reprGen = lambda cname: lambda _: '%s.%s' % (name, cname)
    else:
        reprGen = lambda cname: lambda _: cname
    valueList = [
            type('__constant', (int,), {
                '__slots__': (),
                '__repr__': reprGen(cname),
                '__str__': (lambda ret = cname: lambda _: ret)(),
                })(cvalue)
            for (cvalue, cname) in enumerate(nameList)]
    byName = dict(zip(nameList, valueList))
    byValue = dict(zip(valueList, nameList))

    typedict = {
            '__slots__': (),
            '__repr__': lambda _: name,
            '__getitem__': lambda _, key:
                isinstance(key, (int, long)) and byValue[key] or byName[key],
            'by_name': byName,
            'by_value': byValue,
            }
    typedict.update(byName)
    ret = type(name, (object,), typedict)()

    for value in valueList:
        setattr(value.__class__, '_parent', ret)

    return ret


class frozendict(tuple):
    __slots__  = ()

    def __new__(cls, iterable):
        items = dict(iterable)
        pairs = tuple(sorted(items.items()))
        keys = tuple(x[0] for x in pairs)
        values = tuple(x[1] for x in pairs)
        return tuple.__new__(cls, (keys, values))

    @property
    def _keys(self):
        return tuple.__getitem__(self, 0)
    @property
    def _values(self):
        return tuple.__getitem__(self, 1)

    def __repr__(self):
        return 'frozendict(%r)' % (dict(self.items()),)
    def __str__(self):
        return str(dict(self.items()))

    _NO_DEFAULT = []
    def __getitem__(self, key, default=_NO_DEFAULT):
        try:
            index = self._keys.index(key)
        except ValueError:
            if default is self._NO_DEFAULT:
                raise KeyError(key)
            return default
        else:
            return self._values[index]

    @classmethod
    def fromkeys(cls, keys, value=None):
        return cls(dict.fromkeys(keys, value))

    def __contains__(self, key):
        return key in self._keys
    has_key = __contains__
    def __iter__(self):
        return iter(self._keys)
    def __len__(self):
        return len(self._keys)
    def get(self, key, default=None):
        return self.__getitem__(key, default)
    def keys(self):
        return list(self._keys)
    def values(self):
        return list(self._values)
    def items(self):
        return zip(self._keys, self._values)
    def iterkeys(self):
        return iter(self._keys)
    def itervalues(self):
        return iter(self._values)
    def iteritems(self):
        return iter(zip(self._keys, self._values))
    def copy(self):
        return self

    def __noimpl(self, *args, **kw):
        raise TypeError("this method is not allowed for frozendict")
    __setitem__ = __noimpl
    __delitem__ = __noimpl
    clear = __noimpl
    copy = __noimpl
    pop = __noimpl
    popitem = __noimpl
    setdefault = __noimpl
    update = __noimpl


class Row(object):
    """
    Wrapper around a single result row from a query.

    Behaves as both a tuple and a dictionary, including unpacking.
    
    For example:
    >>> row = Row([1, 2, 3], ['foo', 'bar', 'baz'])
    >>> print row[0]
    1
    >>> print row['foo']
    1
    >>> x, y, z = row
    >>> print x
    1
    """

    __slots__ = ('data', 'fields')

    def __init__(self, data, fields):
        assert len(data) == len(fields)
        self.data = tuple(data)
        self.fields = tuple(fields)

    # Most slots behave like the data tuple
    def __len__(self):
        return len(self.data)

    def __hash__(self):
        return hash(self.data)

    def __iter__(self):
        return iter(self.data)

    def __repr__(self):
        return repr(self.data)

    def __lt__(self, other):
        return self.data < other
    def __le__(self, other):
        return self.data <= other
    def __eq__(self, other):
        return self.data == other
    def __ne__(self, other):
        return self.data != other
    def __gt__(self, other):
        return self.data > other
    def __ge__(self, other):
        return self.data >= other

    # And these behave like a mapping
    def _indexOf(self, key):
        key_ = key.lower()
        for n, field in enumerate(self.fields):
            if field.lower() == key_:
                return n
        else:
            raise KeyError(key)

    def keys(self):
        return list(self.fields)

    def values(self):
        return list(self.data)

    def items(self):
        return zip(self.fields, self.data)

    __SIGIL = []
    def pop(self, key, default=__SIGIL):
        try:
            index = self._indexOf(key)
        except KeyError:
            if default is not self.__SIGIL:
                return default
            raise
        value = self.data[index]
        self.fields = self.fields[:index] + self.fields[index+1:]
        self.data = self.data[:index] + self.data[index+1:]
        return value

    # But the item slot is magic
    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            # Used as a sequence
            return self.data[key]
        else:
            # Used as a mapping
            return self.data[self._indexOf(key)]

    def __setitem__(self, key, value):
        if isinstance(key, (int, slice)):
            # Used as a sequence
            self.data[key] = value
        else:
            # Used as a mapping
            self.pop(key, None)
            self.fields += (key,)
            self.data += (value,)


class DependencySet(object):
    def __init__(self, provides=(), requires=()):
        if hasattr(provides, 'provides'):
            # Actually another dependency set
            self.provides = set(provides.provides)
            self.requires = set(provides.requires)
        else:
            self.provides = set(provides)
            self.requires = set(requires)

    def freeze(self):
        return (sorted(self.provides), sorted(self.requires))
    def copy(self):
        return DependencySet(self)

    def __eq__(self, other):
        return self.freeze() == other.freeze()
    def __lt__(self, other):
        return self.freeze() < other.freeze()
    def __gt__(self, other):
        return self.freeze() > other.freeze()

    def update(self, deps):
        self.provides.update(deps.provides)
        self.requires.update(deps.requires)

    def close(self):
        self.requires.difference_update(self.provides)

    def is_closed(self):
        return not (self.requires - self.provides)

    def is_closed_by(self, other):
        return not (self.requires - self.provides - other.provides)


class DependencyGraph(object):
    def __init__(self, deps=(), base=None):
        self.deps = list(deps)
        self.base = base or DependencySet()

    def flatten(self, withBase=False):
        if withBase:
            flat = self.base.copy()
        else:
            flat = DependencySet()
        for x in self.deps:
            flat.update(x)
        return flat

    def iter_ordered(self):
        flat = self.flatten(True)
        flat.close()
        if flat.requires:
            err = ["Dependency graph is not closed -- "
                    "these requirements are unmet:"]
            for requirement in sorted(flat.requires):
                err.append("    %r" % (requirement,))
            raise RuntimeError("\n".join(err))

        complete = self.base.copy()
        remaining = list(self.deps)
        changed = True
        while remaining:
            changed = False
            for dep in remaining:
                if dep.is_closed_by(complete):
                    complete.update(dep)
                    remaining.remove(dep)
                    changed = True
                    yield dep
            if not changed:
                raise RuntimeError("Dependency loop cannot be solved")

        assert complete.is_closed()


class SQL(object):
    def __init__(self, statement, *args):
        if isinstance(statement, SQL):
            # Copy another SQL object
            assert not args
            self.statement = statement.statement
            self.args = statement.args
        else:
            self.statement = statement
            self.args = args

    def __repr__(self):
        return 'SQL%r' % (tuple((self.statement,) + self.args),)

    def __str__(self):
        # This is not intended to be SQL-safe, just good enough for debugging.
        return self.statement % tuple(repr(x) for x in self.args)

    def __add__(self, other):
        if isinstance(other, basestring):
            return SQL(self.statement + other, *self.args)
        elif isinstance(other, SQL):
            return SQL(self.statement + other.statement,
                    *(self.args + other.args))
        else:
            raise NotImplementedError

    def __radd__(self, other):
        if isinstance(other, basestring):
            return SQL(other + self.statement, *self.args)
        elif isinstance(other, SQL):
            return SQL(other.statement + self.statement,
                    *(other.args + self.args))
        else:
            raise NotImplementedError

    def __iadd__(self, other):
        if isinstance(other, basestring):
            self.statement += other
        elif isinstance(other, SQL):
            self.statement += other.statement
            self.args += other.args
        else:
            raise NotImplementedError
        return self

    @classmethod
    def rjoin(cls, things, joiner=' '):
        things = [SQL(x) for x in things]
        return cls(joiner.join(x.statement for x in things),
                *(itertools.chain(*(x.args for x in things))))
