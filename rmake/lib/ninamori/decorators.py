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


import weakref as _weakref


class _DBOp(object):
    withTransaction = False
    withCursor = False
    readOnly = False
    topLevel = False

    def __new__(cls, func):
        def wrapper(self, *args, **kwargs):
            txn, cursorSource = cls.getTxn(self)

            if cls.withCursor:
                args = (cursorSource.cursor(),) + args

            ret = None
            try:
                ret = func(self, *args, **kwargs)
            except:
                if txn:
                    txn.rollback()
                raise
            else:
                if txn:
                    txn.commit()
                return ret
        wrapper.func_name = func.func_name
        wrapper.func_wrapped = func
        return wrapper

    @classmethod
    def getTxn(cls, other):
        if hasattr(other, 'db'):
            db = other.db
        elif hasattr(other, '_db'):
            db = other._db
        else:
            db = other

        if isinstance(db, _weakref.ref):
            db = db()
            assert db

        if cls.withTransaction:
            txn = cursorSource = db.begin(readOnly=cls.readOnly,
                    topLevel=cls.topLevel)
        else:
            txn, cursorSource = None, db

        return txn, cursorSource


class helper(_DBOp):
    """
    Add a cursor to the argument list, but don't start a transaction.

    Use this for small helper methods. If an error is raised, the parent
    transaction is invalidated, so the caller can't catch errors raised by a
    helper.
    """
    withCursor = True
    withTransaction = False


class protected(_DBOp):
    """
    Start a read-write transaction and add a cursor to the argument list.

    Errors raised in the method will cause a rollback and this can be caught by
    callers.
    """
    withCursor = True
    withTransaction = True
    readOnly = False


class protectedBlock(protected):
    """
    Same as L{protected} but without a cursor.
    """
    withCursor = False


class readOnly(_DBOp):
    """
    Start a read-only transaction and add a cursor to the argument list.

    The transaction will always be rolled back, and callers can catch
    exceptions.
    """
    withCursor = True
    withTransaction = True
    readOnly = True


class readOnlyBlock(readOnly):
    """
    Same as L{readOnly} but without a cursor.
    """
    withCursor = False


class topLevel(_DBOp):
    """
    Start a read-write transaction that must be the topmost transaction.

    In other words, the stack must be empty before this transaction begins,
    and will be empty again when it ends.
    """
    withCursor = True
    withTransaction = True
    topLevel = True
