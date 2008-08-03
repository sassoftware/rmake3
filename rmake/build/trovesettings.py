from conary.lib import cfg

from rmake.build import buildcfg
from rmake.lib import apiutils

class _TroveSettingsRegister(type):
    def __init__(class_, *args, **kw):
        type.__init__(class_, *args, **kw)
        apiutils.register_freezable_classmap('TroveSettings', class_)


class TroveSettings(cfg.ConfigFile, buildcfg.FreezableConfigMixin):
    __metaclass__ = _TroveSettingsRegister
