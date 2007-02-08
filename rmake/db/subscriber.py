#
# Copyright (c) 2006-2007 rPath, Inc.  All Rights Reserved.
#

from rmake.build import subscriber
from rmake.lib.apiutils import thaw

class SubscriberData(object):

    def __init__(self, db):
        self.db = db

    def get(self, subscriberId):
        cu = self.db.cursor()
        cu.execute('''SELECT data FROM SubscriberData WHERE subscriberId=?''',
                   subscriberId)
        dataList = [ x[0] for x in cu.fetchall()]
        if not dataList:
            raise KeyError(subscriberId)
        return thaw('Subscriber', (subscriberId, dataList))

    def remove(self, subscriberId):
        cu = self.db.cursor()
        cu.execute('''DELETE FROM Subscriber
                      WHERE subscriberId=?''')
        cu.execute('''DELETE FROM SubscriberData
                      WHERE subscriberId=?''')
        cu.execute('''DELETE FROM SubscriberEvents
                      WHERE subscriberId=?''')


    def add(self, jobId, subscriber):
        cu = self.db.cursor()
        cu.execute('INSERT INTO Subscriber (jobId, uri) VALUES (?, ?)',
                    jobId, subscriber.uri)
        subscriberId = cu.lastrowid
        subscriber.subscriberId = subscriberId

        for event, subevents in subscriber.iterEvents():
            if not subevents:
                subevents = ['ALL']
            for subevent in subevents:
                cu.execute("""INSERT INTO SubscriberEvents
                               (subscriberId, event, subevent)
                               VALUES (?, ?, ?)""",
                                subscriberId, event, subevent)

        for item in subscriber.freezeData():
            cu.execute('INSERT INTO SubscriberData VALUES (?, ?)',
                       subscriberId, item)

    def _returnSubscribers(self, results):
        d = {}
        for id, data in results:
            if id not in d:
                d[id] = [data]
            else:
                d[id].append(data)

        return [thaw('Subscriber', x) for x in d.iteritems()]

    def getMatches(self, jobId, eventList):
        cu = self.db.cursor()
        subscribersByEvent = {}
        cmd = '''SELECT Subscriber.subscriberId, data
                       FROM Subscriber
                       JOIN SubscriberEvents USING(subscriberId)
                       JOIN SubscriberData USING(subscriberId)
                       WHERE jobId IN (0,?) AND event IN (?,"ALL")
                  '''
        subCmd = cmd + 'AND subEvent IN (?, "ALL")'
        for (event, subEvent), data in eventList:
            params = [jobId, event]
            if subEvent:
                thisCmd = subCmd
                params.append(subEvent)
            else:
                thisCmd = cmd

            subscribers = \
                self._returnSubscribers(cu.execute(thisCmd, params).fetchall())
            if subscribers:
                subscribersByEvent[event, subEvent] = subscribers
                
        return subscribersByEvent

    def getByUri(self, jobId, uri):
        cu = self.db.cursor()
        cmd = '''SELECT Subscriber.subscriberId, data
                   FROM Subscriber
                   JOIN SubscriberEvents USING(subscriberId)
                   JOIN SubscriberData USING(subscriberId)
                   WHERE uri=? AND jobId IN (0,?)
              '''
        params = [uri, jobId]
        return self._returnSubscribers(cu.execute(cmd, params).fetchall())

    def getByJobId(self, jobId):
        cu = self.db.cursor()
        cmd = '''SELECT Subscriber.subscriberId, data
                   FROM Subscriber
                   JOIN SubscriberEvents USING(subscriberId)
                   JOIN SubscriberData USING(subscriberId)
                   WHERE jobId IN (0,?)
              '''
        params = [jobId]
        return self._returnSubscribers(cu.execute(cmd, params).fetchall())



