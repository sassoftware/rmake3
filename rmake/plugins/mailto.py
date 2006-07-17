#
# Copyright (c) 2006 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#
from email import MIMEText
import smtplib

from rmake.build.subscribe import StatusSubscriber


class EmailJobLogger(StatusSubscriber):

    """
        Proof of concept simple email interface to rmake - sends out messages 
        on status changes.
    """

    protocol = 'mailto' 

    listeners = {'JOB_STATE_UPDATED'    : 'jobStateUpdated',
                 'TROVE_STATE_UPDATED'  : 'troveStateUpdated',
                 }

    fields = {
        'from'     : 'rmake@localhost', #address of the email sender
        'fromName' : 'Rmake Daemon', # Displayed name of the email sender
        'toName'   : None,           # Displayed name of the email receiver
        'prefix'   : '[rmake] ',     # Subject prefix
        }

    def _sendEmail(self, subject, body):
        msg = MIMEText.MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = self['from']
        msg['To'] = self.uri

        s = smtplib.SMTP()
        s.connect()
        s.sendmail(self['from'], [self.uri], msg.as_string())
        s.close()

    def jobStateUpdated(self, job):
        pass

    def troveStateUpdated(self, job, trove):
        if trove.isBuilt():
            self._sendEmail('%s Built' % trove.getName(),
                            '%s Built' % trove.getName())
        elif trove.isFailed():
            self._sendEmail('%s Failed' % trove.getName(),
                            '%s Failed' % trove.getName())
