from conary.lib import cfg
from rmake.build import buildcfg


class TroveSettings(cfg.ConfigFile, buildcfg.FreezableConfigMixin):

    def __init__(self):
        cfg.ConfigFile.__init__(self)
        buildcfg.FreezableConfigMixin.__init__(self)
