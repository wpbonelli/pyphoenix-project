"""
MF6 input file (MF6IO) format is a bespoke file format used to
configure a MODFLOW 6 simulation.

:mod:`mf6io` exposes an API familiar to users of the standard
library :mod:`json`, :mod:`marshal` and :mod:`pickle` modules.
It is patterned after the standard library :mod:`json` module.
"""

__all__ = ["CONVERTERS"]


from cattrs.preconf.json import make_converter as make_json_converter
from cattrs.preconf.pyyaml import make_converter as make_yaml_converter
from cattrs.preconf.tomlkit import make_converter as make_toml_converter

from flopy4.decorators import io
from flopy4.mf6.io.converter import make_converter as make_mf6_converter

CONVERTERS = {
    "toml": make_toml_converter(),
    "yaml": make_yaml_converter(),
    "json": make_json_converter(),
    "mf6": make_mf6_converter(),
}


def mf6io(cls, default: str = "mf6"):
    """
    Class decorator to add `load` and `write` methods for
    MODFLOW 6 with a default set of registered converters.
    """
    return io(cls, CONVERTERS, default)
