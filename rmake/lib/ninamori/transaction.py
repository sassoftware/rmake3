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


import weakref
from rmake.lib.ninamori.error import TransactionError
from rmake.lib.ninamori.util import getOrigin


class Transaction(object):
    __slots__ = ('__weakref__', 'db', 'state', 'origin',
            'savePoint', 'readOnly')

    STATE_ACTIVE    = 1
    STATE_INERROR   = 2
    STATE_CLOSED    = 3

    def __init__(self, db, savePoint, readOnly=False, depth=1):
        self.db = weakref.ref(db)
        self.state = self.STATE_ACTIVE
        self.savePoint = savePoint
        self.readOnly = readOnly
        self.origin = getOrigin(depth + 1)

    def isActive(self):
        return self.state == self.STATE_ACTIVE

    def isInError(self):
        return self.state == self.STATE_INERROR

    def isClosed(self):
        return self.state == self.STATE_CLOSED

    def setInError(self):
        """
        Set the transaction to error state. No statements may be
        executed until it is rolled back.
        """
        if self.isClosed():
            raise TransactionError("Cannot set a closed transaction to "
                    "error state.", self)
        self.state = self.STATE_INERROR

    def cursor(self):
        """
        Get a new cursor for this transaction.
        """
        #pylint: disable-msg=W0212
        self.ready()
        return self.db()._txn_cursor(self)

    def rollback(self):
        """
        Roll back this transaction.
        """
        #pylint: disable-msg=W0212
        if self.isClosed():
            raise TransactionError("Cannot roll back a closed transaction.")
        else:
            self.db()._txn_rollback(self)

    def commit(self):
        """
        Commit this transaction.
        """
        #pylint: disable-msg=W0212
        if self.isClosed():
            raise TransactionError("Cannot commit a closed transaction.")
        elif self.isInError():
            raise TransactionError("Cannot commit due to pending error; "
                    "a rollback is required.")
        else:
            self.db()._txn_commit(self)

    def ready(self):
        """
        Assert that this transaction is ready to execute a statement,
        i.e. it is not in error and is the topmost in the stack.
        
        Called by a child cursor before executing a statement.
        """
        #pylint: disable-msg=W0212
        self.db()._txn_check(self)
        if self.isInError():
            raise TransactionError("The current transaction must be rolled "
                    "back before executing further statements.", self)
        elif self.isClosed():
            raise TransactionError("Cannot execute statements on a closed "
                    "transaction.", self)

    # context management protocol
    def __enter__(self):
        """
        Context manager interface -- execute statements within a
        transaction.

        Example:
        >>> with db.begin() as cu:
        ...     cu.execute(...)
        ...     subQuery()
        ...

        This will begin a transaction, assign a cursor for that transaction to
        C{cu}, and commit the transaction when control leaves the block. If an
        exception is raised, the transaction will be rolled back.
        """
        return self.cursor()

    def __exit__(self, excType, excValue, excTB):
        """
        Commit or rollback when leaving a context-managed block.
        """
        #pylint: disable-msg=W0613
        if excType:
            self.rollback()
        else:
            self.commit()
