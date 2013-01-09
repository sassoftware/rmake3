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
