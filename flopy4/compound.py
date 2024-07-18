from collections.abc import MutableMapping
from dataclasses import dataclass

from flopy4.parameter import MFParameter


@dataclass
class MFKeystring(MutableMapping, MFParameter):
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)


@dataclass
class MFRecord(MutableMapping, MFParameter):
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)
