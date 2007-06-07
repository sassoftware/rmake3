import urllib2
import urllib

from conary.repository.netrepos import netauth

from rmake import errors

class AuthenticationManager(object):
    def __init__(self, url, db):
        self.pwCheckUrl = url
        self.db = db

    def authCheck(self, user, challenge):
        isValid = False
        if self.pwCheckUrl:
            if not user or not challenge:
                raise errors.InsufficientPermission("""\
No user given - check to make sure you've set rmakeUser config variable to match a user and password accepted by the rBuilder instance at %s""" % self.pwCheckUrl)

            try:
                url = "%s/pwCheck?user=%s;password=%s" \
                        % (self.pwCheckUrl, urllib.quote(user),
                           urllib.quote(challenge))
                f = urllib2.urlopen(url)
                xmlResponse = f.read()
                p = netauth.PasswordCheckParser()
                p.parse(xmlResponse)
                isValid = p.validPassword()
            except Exception, e:
                # FIXME: this is a very broad exception handler
                isValid = False

        if not isValid:
            raise errors.InsufficientPermission("""\
Access denied.  Make sure your rmakeUser configuration variable contains a user and password accepted by the rBuilder instance at %s""" % self.pwCheckUrl)
        return isValid

