from ast import literal_eval
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Optional, Tuple

import toml

from flopy4.mf6.io.constants import Reader


@dataclass
class MFParamSpec:
    """
    MF6 input parameter specification.
    """

    block: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    longname: Optional[str] = None
    description: Optional[str] = None
    deprecated: bool = False
    in_record: bool = False
    layered: bool = False
    optional: bool = True
    numeric_index: bool = False
    preserve_case: bool = False
    repeating: bool = False
    tagged: bool = True
    reader: Reader = Reader.urword
    # todo change to variadic tuple of str and resolve
    # actual shape at load time from simulation context
    shape: Optional[Tuple[int]] = None
    default_value: Optional[Any] = None

    @classmethod
    def from_dfn(cls, f) -> "MFParamSpec":
        """
        Load an MF6 input input parameter specification
        from a definition file.
        """
        spec = dict()
        members = fields(cls)
        keywords = [m.name for m in members if m.type is bool]

        while True:
            line = f.readline()
            if not line or line == "\n":
                break
            words = line.strip().lower().split()
            key = words[0]
            val = " ".join(words[1:])
            if key in keywords:
                spec[key] = val == "true"
            elif key == "reader":
                spec[key] = Reader.from_string(val)
            elif key == "shape":
                spec[key] = literal_eval(val)
            else:
                spec[key] = val

        return cls(**spec)


class Dfn:
    def __init__(self, component, subcomponent, dfn, *args, **kwargs):
        self._component = component
        self._subcomponent = subcomponent
        self._dfn = dfn

    def __getitem__(self, key):
        return self._dfn["block"][key]

    def __setitem__(self, key, value):
        self._dfn["block"][key] = value

    def __delitem__(self, key):
        del self._dfn["block"][key]

    def __iter__(self):
        return iter(self._dfn["block"])

    def __len__(self):
        return len(self._dfn["block"])

    @property
    def component(self):
        return self._component

    @property
    def subcomponent(self):
        return self._subcomponent

    @property
    def blocknames(self):
        return self._dfn["blocknames"]

    @property
    def dfn(self):
        return self._dfn

    def blocktags(self, blockname) -> list:
        return list(self._dfn["block"][blockname])

    def block(self, blockname) -> dict:
        return self._dfn["block"][blockname]

    def param(self, blockname, tagname) -> dict:
        return self._dfn["block"][blockname][tagname]

    @classmethod
    def load(cls, f, metadata=None):
        p = Path(f)

        if not p.exists():
            raise ValueError("Invalid DFN path")

        component, subcomponent = p.stem.split("-")
        data = toml.load(f)

        return cls(component, subcomponent, data, **metadata)


class DfnSet:
    def __init__(self, *args, **kwargs):
        self._dfns = dict()

    def __getitem__(self, key):
        return self._dfns[key]

    def __setitem__(self, key, value):
        self._dfns[key] = value

    def __delitem__(self, key):
        del self._dfns[key]

    def __iter__(self):
        return iter(self._dfns)

    def __len__(self):
        return len(self._dfns)

    def add(self, key, dfn):
        if key in self._dfns:
            raise ValueError("DFN exists in container")

        self._dfns[key] = dfn

    def get(self, key):
        if key not in self._dfns:
            raise ValueError("DFN does not exist in container")

        return self._dfns[key]

    # def get(self, component, subcomponent):
    #    key = f"{component.lower()}-{subcomponent.lower()}"
    #    if key not in self._dfns:
    #        raise ValueError("DFN does not exist in container")
    #
    #    return self._dfns[key]
