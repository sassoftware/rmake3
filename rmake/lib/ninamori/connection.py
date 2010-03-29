#
# Copyright (c) 2009-2010 rPath, Inc.
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

from rmake.lib.ninamori.cursor import Cursor
from rmake.lib.ninamori.decorators import helper, protected, readOnlyBlock, topLevel
from rmake.lib.ninamori.error import TransactionError
from rmake.lib.ninamori.schema.schema import SchemaVersion
from rmake.lib.ninamori.schema.timeline import Timeline
from rmake.lib.ninamori.transaction import Transaction
from rmake.lib.ninamori.types import DependencyGraph, SQL


class DatabaseConnection(object):
    __slots__ = ('__weakref__',
            '_conn', '_stack', '_savepoint_counter',
            '_metadata', '_tables',
            )
    driver = None

    def __init__(self, conn):
        self._conn = conn
        self._stack = []
        self._savepoint_counter = 0

        self._metadata = None
        self._tables = None

    # Connecting/disconnecting

    @classmethod
    def connect(cls, connectString):
        raise NotImplementedError

    def close(self):
        if self._conn:
            self._conn.close()
        self._conn = None
        self._stack = []
        self._savepoint_counter = 0

        self._metadata = None
        self._tables = None

    # Meta-information

    @property
    def tables(self):
        if self._tables is None:
            self.loadMeta()
        return self._tables

    @property
    def metadata(self):
        if self._metadata is None:
            self.loadMeta()
        return self._metadata

    @readOnlyBlock
    def loadMeta(self, skipData=False):
        """Load metadata and table listing from the database."""
        self._loadMeta()
        if not skipData:
            self._loadMetaData()

    @helper
    def _loadMetaData(self, cu):
        self._metadata = {}
        if 'database_metadata' in self._tables:
            cu.execute("SELECT schema, name, value FROM database_metadata")
            for schema, name, value in cu:
                schema = self._metadata.setdefault(schema, {})
                if name == 'schema_version':
                    try:
                        value = SchemaVersion(value)
                    except ValueError:
                        continue
                schema[name] = value

    def _loadMeta(self):
        raise NotImplementedError

    @protected
    def saveMeta(self, cu, schemaName=None):
        if self._metadata is None:
            # The table list is probably missing too.
            self.loadMeta()
        if 'database_metadata' not in self._tables:
            raise RuntimeError("Can't save metadata: "
                    "table database_metadata not found")

        sql = SQL('DELETE FROM database_metadata')
        if schemaName:
            sql += SQL(' WHERE schema = %s', schemaName)
        cu.execute(sql)

        for schema, meta in self._metadata.items():
            if schemaName and schema != schemaName:
                continue
            for key, value in meta.items():
                if isinstance(value, SchemaVersion):
                    value = value.asString()
                cu.execute("""INSERT INTO database_metadata
                        ( schema, name, value )
                    VALUES ( %s, %s, %s )""", (schema, key, value))

    # Schema management

    @topLevel
    def attach(self, cu, schemaName, path, version, allowMigrate=True):
        if isinstance(version, basestring):
            version = SchemaVersion(version)
        timeline = Timeline(path)
        schema = timeline.get(version)

        # TODO: specific exceptions for schema version errors
        metadata = self.metadata.setdefault(schemaName, {})
        current = metadata.get('schema_version')
        if current > version:
            # Future schemas are always illegal (for now)
            raise RuntimeError("Database schema %r is in the future"
                    % (schemaName,))
        if not allowMigrate:
            if current is None:
                raise RuntimeError("Database schema %r is not loaded"
                    % (schemaName,))
            elif current < version:
                raise RuntimeError("Database schema %r is out of date"
                    % (schemaName,))
            assert current == version

            # Everything is OK
            return

        assert current is None # migration not implemented yet

        reflected = self.getSchema()
        graph = DependencyGraph(schema.diff(reflected, newOnly=True))
        for action in graph.iter_ordered():
            cu.execute(action.asSQL())

        # Reload table list so we can make sure the metatable was created.
        self.loadMeta(skipData=True)

        # Save metadata with new schema information.
        metadata['schema_version'] = version
        self.saveMeta(schemaName)

    def getSchema(self):
        raise NotImplementedError


    # Transaction methods
    def _execute(self, *args, **kwargs):
        """
        Internal use -- pass-through to execute a statement
        """
        return self._conn.cursor().execute(*args, **kwargs)

    def _getSavePointName(self):
        """
        Generate a name unique to this connection suitable for use as an
        argument to C{SAVEPOINT}.
        """
        self._savepoint_counter += 1
        return 'sp_%d' % (self._savepoint_counter,)

    def _checkTxn(self, txn):
        """
        Asserts that C{txn} is the topmost transaction in this db.
        """
        if txn not in self._stack:
            raise TransactionError("Transaction is not managed here.", txn)
        elif txn is not self._stack[-1]:
            raise TransactionError("Transaction is not topmost.", txn)

    def _popTxn(self, txn, unwind=False):
        """
        Asserts that C{txn} is the topmost transaction in this db and
        pops it. If C{unwind} is C{True}, then any transactions on top
        of the given one are popped instead of raising an assertion.
        """
        while unwind and txn is not self._stack[-1]:
            self._stack.pop()
        self._checkTxn(txn)
        self._stack.pop()


    def begin(self, readOnly=False, topLevel=False, depth=1):
        """
        Begin a new transaction.  Returns a new L{Transaction} object that can
        be used to obtain a cursor.

        @rtype: L{Transaction}
        """
        if not self._stack:
            self._execute("BEGIN")
        elif topLevel:
            raise TransactionError("There must not be a transaction open.",
                    self._stack[0])
        txn = Transaction(self, self._getSavePointName(), readOnly, depth + 1)
        self._execute("SAVEPOINT %s" % (txn.savePoint,))
        self._stack.append(txn)
        return txn

    def cursor(self):
        """
        Return a new cursor for the topmost transaction, which must not
        be in error.
        """
        return self._stack[-1].cursor()

    # Non-transaction methods.
    def execute(self, query, *args, **kwargs):
        """Execute a statement outside of any transaction.

        Useful for statements that must not be run in a transaction, e.g.
        CREATE DATABASE.
        """
        if self._stack:
            raise TransactionError("There must not be a transaction open.",
                    self._stack[0])
        self._start_autocommit()
        try:
            cu = self._conn.cursor()
            return cu.execute(query, *args, **kwargs)
        finally:
            self._end_autocommit()

    def _start_autocommit(self):
        raise NotImplementedError

    def _end_autocommit(self):
        raise NotImplementedError

    # Callbacks for our txns to open/close underlying txns, among other
    # things.
    def _txn_check(self, txn):
        """
        Assert that C{txn} is the topmost transaction in this db.

        This just calls C{_checkTxn}, but it is explicitly intended to
        be called by child transactions.
        """
        self._checkTxn(txn)

    def _txn_cursor(self, txn):
        """
        Open a new L{Cursor} under transaction C{txn}.
        """
        self._checkTxn(txn)
        return Cursor(txn, self._conn)

    def _txn_rollback(self, txn):
        """
        Internal use -- called by a child transaction to rollback the
        underlying transaction, then release the transaction object.
        """
        self._popTxn(txn, unwind=True)

        # Roll back this transaction and any changes "rolled up" into it
        # from subtransactions.
        self._execute("ROLLBACK TO SAVEPOINT %s" % (txn.savePoint,))

        if not self._stack:
            # If there are no transactions in the stack, and thus no savepoints
            # to roll back to, rollback the real transaction even though it
            # doesn't contain any changes.
            self._execute("ROLLBACK")

    def _txn_commit(self, txn):
        """
        Internal use -- called by a child transaction to commit the
        underlying transaction, then release the transaction object.
        """
        self._popTxn(txn, unwind=False)
        if not txn.readOnly:
            # Read-write transactions get "released" so their changes
            # become part of the parent transaction.
            self._execute("RELEASE SAVEPOINT %s" % (txn.savePoint,))
        else:
            # Read-only transactions get rolled back. This will undo any
            # subtransactions that committed, as they got "rolled up" into
            # this one.
            self._execute("ROLLBACK TO SAVEPOINT %s" % (txn.savePoint,))
        if not self._stack:
            # If there are no transactions in the stack, and thus no savepoints
            # to roll back to, commit the whole pile of changes, or rollback if
            # the last transaction was read-only.
            if txn.readOnly:
                self._execute("ROLLBACK")
            else:
                self._execute("COMMIT")


class ConnectString(object):
    __slots__ = ('driver', 'user', 'password', 'host', 'port', 'dbname')

    def __init__(self, driver, user=None, password=None, host=None,
            port=None, dbname=None):
        assert dbname
        self.driver = driver
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.dbname = dbname

    @classmethod
    def parse(cls, val):
        if not val:
            raise ValueError("connect string cannot be empty")
        if '://' not in val:
            raise ValueError("connect string must start with 'driver://'")
        driver, val = val.split('://', 1)

        user = password = host = port = None
        if '/' not in val:
            dbname = val
        else:
            host, dbname = val.rsplit('/', 1)
            if '@' in host:
                user, host = host.rsplit('@', 1)
                if ':' in user:
                    user, password = user.split(':', 1)

            # Borrowed from httplib -- this parses the port from the host while
            # honoring bracketed IPv6 addresses e.g. [::1]:5432
            i = host.rfind(':')
            j = host.rfind(']')
            if i > j:
                host, port = host[:i], int(host[i+1:])
            else:
                port = None
            if host and host[0] == '[' and host[-1] == ']':
                host = host[1:-1]

        return cls(driver, user, password, host, port, dbname)

    def _asSeq(self, exclude=()):
        return [(key, getattr(self, key))
                for key in self.__slots__
                if key not in exclude
                and getattr(self, key) is not None]

    def __str__(self):
        val = self.driver + '://'
        if self.host:
            if self.user:
                val += self.user
                if self.password:
                    val += ':' + self.password
                val += '@'
            if ':' in self.host:
                val += '[' + self.host + ']'
            else:
                val += self.host

            if self.port:
                val += ':%d' % self.port
            val += '/'
        val += self.dbname
        return val

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__,
                ', '.join('%s=%r' % tup for tup in self._asSeq()))

    def asDSN(self, exclude=('driver',)):
        parts = []
        for key, value in self._asSeq(exclude):
            parts.append('%s=%s' % (key, value))
        return ' '.join(parts)

    def asDict(self, exclude=()):
        return dict(self._asSeq(exclude))

