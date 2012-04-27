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


from conary.lib import cfg

from rmake.build import buildcfg
from rmake.lib import apiutils

class _TroveSettingsRegister(type):
    def __init__(class_, *args, **kw):
        type.__init__(class_, *args, **kw)
        apiutils.register_freezable_classmap('TroveSettings', class_)


class TroveSettings(cfg.ConfigFile, buildcfg.FreezableConfigMixin):
    __metaclass__ = _TroveSettingsRegister

    def __init__(self):
        cfg.ConfigFile.__init__(self)
        buildcfg.FreezableConfigMixin.__init__(self)
