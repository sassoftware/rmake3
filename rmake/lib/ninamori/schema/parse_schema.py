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

import inspect
from rmake.lib.ninamori.schema import types
from rmake.lib.ninamori.schema.schema import Schema
from rmake.lib.ninamori.schema.table import Table


_COLTYPE_CACHE = {}


def parse(definition):
    globals = dict(
            __metaclass__ = SchemaTableFactory,
            References = types.References,
            )
    globals.update(types.ColFlags.by_name)
    globals.update(types.FKeyActions.by_name)
    for name, value in inspect.getmembers(types, inspect.isclass):
        if not name.startswith('_'):
            globals[name] = value
    exec definition in globals

    schema = Schema()
    schema.tables = {}
    for name, object in globals.items():
        if isinstance(object, Table):
            schema.tables[object.name] = object
    return schema


def parseColumnType(val):
    if val in _COLTYPE_CACHE:
        cclass, cparams = _COLTYPE_CACHE[val]
        return cclass(*cparams)

    paramstart = val.find('(')
    if paramstart > -1:
        paramend = val.find(')')
        ctype = val[:paramstart]
        plist = val[paramstart + 1 : paramend].split(',')
        cparams = []
        for param in plist:
            param = param.strip()
            if param.isdigit():
                param = int(param)
            cparams.append(param)
    else:
        ctype = val
        cparams = []

    ctype = ctype.lower()
    for _, cclass in inspect.getmembers(types, inspect.isclass):
        if not issubclass(cclass, types._Column):
            continue
        names = cclass.__dict__.get('_names', ())
        if ctype in names:
            break
    else:
        cclass = types.Column
        cparams = [val]

    _COLTYPE_CACHE[val] = cclass, cparams
    return cclass(*cparams)


class SchemaTableFactory(type):
    """Metaclass for tables in a schema definition file."""
    def __new__(cls, name, bases, clsdict):
        name = clsdict.get('_name', name)
        table = Table(name)

        for name, definition in clsdict.items():
            if name.startswith('_'):
                continue

            if isinstance(definition, types._Field):
                definition = (definition,)
            elif isinstance(definition, (list, tuple)):
                assert isinstance(definition[0], types._Field)
            else:
                raise TypeError("Don't know how to use schema object "
                        "of type %s" % definition.__class__.__name__)

            base, extra = definition[0], definition[1:]
            if isinstance(base, types._Column):
                base.name = name
                for field in extra:
                    if field is types.ColFlags.NOT_NULL:
                        base.not_null = True
                    elif isinstance(field, types.Default):
                        base.default = field.value
                    elif isinstance(field, types._Constraint):
                        field.keys = (name,)
                        field.name = field.getDefaultName(table)
                        table.constraints[field.name] = field
                    else:
                        raise TypeError("Don't know how to use schema object "
                                "of type %s" % field.__class__.__name__)
                table.columns[name] = base
            else:
                if extra:
                    raise TypeError("Flags and column constraints are only "
                            "allowed on columns, not %s"
                            % base.__class__.__name__)
                if isinstance(base, types.Index):
                    base.name = name
                    table.indexes[base.name] = base
                elif isinstance(base, types._Constraint):
                    base.name = name
                    table.constraints[base.name] = base
                else:
                    assert False

        table._reindexColumns()
        table._tableDone()
        return table
