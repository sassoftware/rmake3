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


class DatabaseError(RuntimeError):
    pass


class TransactionError(DatabaseError):
    def __init__(self, message, txn=None):
        DatabaseError.__init__(self, message, txn)
        self.msg = message
        self.txn = txn

    def __str__(self):
        msg = self.msg
        if self.txn:
            msg += " (transaction begun at %s)" % self.txn.origin
        return msg


class SchemaError(DatabaseError):
    pass


class MigrationError(SchemaError):
    pass


# SQL standard errors
# http://www.postgresql.org/docs/8.4/interactive/errcodes-appendix.html

class SQLError(DatabaseError):
    err_class = None
    err_code = None

## Class 23 - Integrity Constraint Violation

class IntegrityError(SQLError):
    err_class = '23'
    err_code = '23000'
class RestrictViolationError(IntegrityError):
    err_code = '23001'
class NotNullViolationError(IntegrityError):
    err_code = '23502'
class ForeignKeyViolationError(IntegrityError):
    err_code = '23503'
class UniqueViolationError(IntegrityError):
    err_code = '23505'
class CheckViolationError(IntegrityError):
    err_code = '23514'

## Class 42 - Syntax Error or Access Rule Violation

class AccessViolationError(SQLError):
    err_class = '42'
    err_code = '42000'
class SyntaxError(AccessViolationError):
    err_code = '42601'
class InsufficientPrivilegeError(AccessViolationError):
    err_code = '42501'
class UndefinedColumnError(AccessViolationError):
    err_code = '42703'
class UndefinedTableError(AccessViolationError):
    err_code = '42P01'
class UndefinedObjectError(AccessViolationError):
    err_code = '42704'
class DuplicateObjectError(AccessViolationError):
    err_code = '42710'
class DuplicateTableError(AccessViolationError):
    err_code = '42P07'


DATABASE_ERRORS = dict((x.err_code, x) for x in locals().values()
        if getattr(x, 'err_code', None))


def getExceptionFromCode(pgcode):
    cls = DATABASE_ERRORS.get(pgcode, None)
    if cls:
        return cls
    pgclass = pgcode[:2] + '000'
    cls = DATABASE_ERRORS.get(pgclass, None)
    if cls:
        return cls
    return SQLError
