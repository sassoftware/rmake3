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


class DatabaseLockedError(DatabaseError):
    pass


class InvalidTableError(DatabaseError):
    pass


# SQL standard errors

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


DATABASE_ERRORS = dict((x.err_code, x) for x in locals().values()
        if getattr(x, 'err_code', None))
