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

    def _returnSubscribers(self, results, subscriberCache = None):
        if subscriberCache is None:
            subscriberCache = {}
        d = {}
        for id, data in results:
            if id not in d:
                d[id] = [data]
            else:
                d[id].append(data)

        toReturn = []
        for id, data in d.iteritems():
            if id not in subscriberCache:
                subscriberCache[id] = thaw('Subscriber', (id, data))
            toReturn.append(subscriberCache[id])
        return toReturn

    def getMatches(self, jobId, eventList):
        cu = self.db.cursor()
        subscribersByEvent = {}
        cmd = '''SELECT Subscriber.subscriberId, data
                       FROM Subscriber
                       JOIN SubscriberEvents USING(subscriberId)
                       JOIN SubscriberData USING(subscriberId)
                       WHERE jobId IN (0,?) AND event IN (?,'ALL')
                  '''
        subCmd = cmd + "AND subEvent IN (?, 'ALL')"
        subscriberCache = {}
        for (event, subEvent), data in eventList:
            params = [jobId, event]
            if subEvent:
                thisCmd = subCmd
                params.append(str(subEvent))
            else:
                thisCmd = cmd

            subscribers = \
                self._returnSubscribers(cu.execute(thisCmd, params).fetchall(),
                                        subscriberCache)
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
