#!/usr/bin/python2.4
"""
    Conary Password prompting utility.  Pops up a little window that asks
    you for your username and password.
"""

import os
import sys

import pygtk
pygtk.require('2.0')
import gtk

if __name__ == '__main__' and 'CONARY_PATH' in os.environ:
    sys.path.insert(0, os.environ['CONARY_PATH'])

from conary import conarycfg

class PasswordPrompterGui(object):

    def __init__(self, formData):
        self.formData = formData
        self._setupWindow(formData)

    def _setupWindow(self, formData):
        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        window.set_border_width(10)

        requestLabel = gtk.Label('Please enter your username and password'
                                 ' for %s:' % formData.hostname)
        table = gtk.Table(2, 2)
        userLabel = gtk.Label('User:')
        userEntry = gtk.Entry(max=256)
        if formData.user:
            userEntry.set_text(formData.user)
        passwordLabel = gtk.Label('Password:')
        passwordEntry = gtk.Entry(max=256)
        if formData.password:
            passwordEntry.set_text(formData.password)
        passwordEntry.set_visibility(False)
        table.attach(userLabel, 0, 1, 0, 1)
        table.attach(userEntry, 1, 2, 0, 1)
        table.attach(passwordLabel, 0, 1, 1, 2)
        table.attach(passwordEntry, 1, 2, 1, 2)
        passwordLabel.set_alignment(0, 1)
        passwordEntry.set_alignment(0)
        userLabel.set_alignment(0, 1)
        userEntry.set_alignment(0)

        contextLabel = gtk.Label('Or select the correct context')
        contextList = gtk.combo_box_new_text()
        contextList.append_text('Select a context')
        for name in formData.contextList:
            contextList.append_text(name)
        contextList.set_active(0)
        contextList.connect("changed", self.contextSelected)

        submitButton = gtk.Button('submit')
        submitButton.connect("clicked", self.submit)
        cancelButton = gtk.Button('cancel')
        cancelButton.connect("clicked", self.cancel)
        commandBox = gtk.HButtonBox()
        commandBox.pack_start(cancelButton, False)
        commandBox.pack_start(submitButton, False)

        majorBox = gtk.VBox(False, 0)
        box1 = gtk.VBox(False, 0)
        box1.pack_start(requestLabel, True, True, 0)
        box1.pack_start(table, True, True, 0)
        box2 = gtk.VBox(True, 0)
        box2.pack_start(contextLabel, True, True, 0)
        box2.pack_start(contextList, False, False, 0)

        majorBox.add(box1)
        majorBox.add(box2)
        majorBox.add(commandBox)
        window.add(majorBox)
        window.show_all()

        self.userEntry = userEntry
        self.passwordEntry = passwordEntry
        self.contextList = contextList
        self.window = window

    def _getContext(self):
        model = self.contextList.get_model()
        active = self.contextList.get_active()
        if active < 0:
            return None
        return model[active][0]

    def contextSelected(self, widget):
        context = self._getContext()
        if context:
            context = self.formData.contextList.get(context, None)
            if not context:
                user, password = '', ''
            else:
                section = self.formData.cfg.getSection(context)
                user, password = section.user.find(self.formData.hostname)
            self.userEntry.set_text(user)
            self.passwordEntry.set_text(password)

    def _getFormData(self):
        self.formData.user = self.userEntry.get_text()
        self.formData.password = self.passwordEntry.get_text()

    def submit(self, widget):
        self._getFormData()
        del self.window
        gtk.main_quit()

    def cancel(self, widget):
        self.formData.user = None
        self.formData.password = None
        self.window.hide()
        gtk.main_quit()

    def main(self):
        gtk.main()


class PasswordData(object):
    def __init__(self, cfg, hostname, user=None, password=None, context=None, 
                 contextList=[]):
        self.cfg = cfg
        self.hostname = hostname
        self.user = user
        self.password = password
        self.context = context
        self.contextList = contextList

class PasswordPrompter(object):
    def __init__(self, cfg):
        self.cfg = cfg

    def getContexts(self, server, user=None):
        sectionNames = {}
        for sectionName in self.cfg.iterSectionNames():
            section = self.cfg.getSection(sectionName)
            data = section.user.find(server)
            if not data:
                continue
            if user:
                if data[0] == user and data[1]:
                    sectionNames.append(sectionName)
            else:
                sectionNames[sectionName + ' (%s)' % data[0]] = sectionName
        return sectionNames


    def getPassword(self, server, userName=None):
        contextNames = self.getContexts(server)
        if 'rmake' in contextNames.values():
            # if rmake is an available context, set that w/o prompting.
            section = self.cfg.getSection('rmake')
            return section.user.find(self.formData.hostname)

        info = PasswordData(self.cfg, server, contextList=contextNames,
                            user=userName)
        PasswordPrompterGui(info).main()
        return info.user, info.password

def main(argv):
    cfg = conarycfg.ConaryConfiguration(True)
    return PasswordPrompter(cfg).getPassword(sys.argv[1])

if __name__ == "__main__":
    sys.exit(main(sys.argv))
