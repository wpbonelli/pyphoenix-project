from collections import OrderedDict, UserDict
from itertools import groupby
from pprint import pformat
from typing import Mapping

from flopy4.block import get_block
from flopy4.param import MFParamSpec
from flopy4.utils import strip


class DFN(UserDict):
    """
    Mapping of parameter names to parameter specifications.
    Also dynamically creates block specifications to match.
    Acts like a dictionary and supports named attributes.
    """

    def __init__(self, component, subcomponent, params):
        self.component = component
        self.subcomponent = subcomponent

        # param spec
        DFN.check(params)
        self.params = params
        super().__init__(params)
        for key, param in self.items():
            setattr(self, key, param)

        # block spec
        pkg_name = component.title() + subcomponent.title()
        blocks = {
            block_name: get_block(
                component_name=pkg_name,
                block_name=block_name,
                params={param.name: param for param in block_params},
            )
            for block_name, block_params in groupby(
                params.values(), lambda p: p.block
            )
        }
        self.blocks = blocks
        for key, block in blocks.items():
            setattr(self, key, block)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        tother = type(other)
        if issubclass(tother, Mapping):
            return OrderedDict(sorted(self)) == OrderedDict(sorted(other))
        return False

    @property
    def name(self):
        return f"{self.component}-{self.subcomponent}"

    @staticmethod
    def check(items):
        """Raise if any items are not instances of `MFParamSpec`."""
        if not items:
            return
        elif isinstance(items, dict):
            items = items.values()
        not_specs = [
            p
            for p in items
            if p is not None and not isinstance(p, MFParamSpec)
        ]
        if any(not_specs):
            raise TypeError(f"Expected MFParamSpec, got {not_specs}")

    @classmethod
    def load(cls, f):
        component = None
        subcomponent = None
        params = dict()

        while True:
            pos = f.tell()
            line = f.readline()
            if line == "":
                break
            if line == "\n":
                continue
            words = strip(line).lower().split()
            if not any(words):
                continue
            if words[0].startswith("#"):
                component, subcomponent = words[2:3]

            f.seek(pos)
            spec = MFParamSpec.load(f)
            params[spec.name] = spec

        return cls(
            component=component,
            subcomponent=subcomponent,
            params=params,
        )


class DFNs(UserDict):
    """
    Mapping of DFN names to DFNs, where the definition
    file's name follows the <component>-<subcomponent>
    format convention.
    """

    def __init__(self, dfns):
        DFNs.check(dfns)
        super().__init__(dfns)

    def __repr__(self):
        return pformat(self.data)

    @staticmethod
    def check(blocks):
        """
        Raise if any items are not instances of `DFN`.
        """
        if not blocks:
            return
        elif isinstance(blocks, dict):
            blocks = blocks.values()
        not_dfns = [
            b for b in blocks if b is not None and not issubclass(type(b), DFN)
        ]
        if any(not_dfns):
            raise TypeError(f"Expected DFN, got {not_dfns}")
