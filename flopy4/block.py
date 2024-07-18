from abc import ABCMeta
from collections.abc import MutableMapping
from dataclasses import asdict
from typing import Dict

from flopy4.parameter import MFParameter
from flopy4.utils import strip


def get_member_params(cls) -> Dict[str, MFParameter]:
    if not issubclass(cls, (MFBlock, MFBlocks)):
        raise ValueError(f"Expected MFBlock(s), got {cls}")

    return {
        k: v
        for k, v in cls.__dict__.items()
        if issubclass(type(v), MFParameter)
    }


class MFBlockMeta(type):
    def __new__(cls, clsname, bases, attrs):
        # todo: setup hooks to settings data. we want to
        # be able to define a block in terms of MFScalar,
        # MFArray and MFList while returning native types
        # to the user, like what Django does for Models.
        return super().__new__(cls, clsname, bases, attrs)


class MFBlockMappingMeta(MFBlockMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFBlock(MutableMapping, metaclass=MFBlockMappingMeta):
    def __init__(self, name=None, index=None, *args, **kwargs):
        self.name = name
        self.index = index
        self._params = dict()
        self.update(dict(*args, **kwargs))
        for key, param in self.items():
            setattr(self, key, param)

    def __getitem__(self, key):
        return self._params[key]

    def __setitem__(self, key, value):
        self._params[key] = value

    def __delitem__(self, key):
        del self._params[key]

    def __iter__(self):
        return iter(self._params)

    def __len__(self):
        return len(self._params)

    @classmethod
    def load(cls, f):
        name = None
        index = None
        found = False
        params = dict()
        members = get_member_params(cls)
        while True:
            pos = f.tell()
            line = strip(f.readline()).lower()
            words = line.split(" ")
            keyword = words[0]
            if keyword == "begin":
                found = True
                name = words[1]
                if len(words) > 2 and str.isdigit(words[2]):
                    index = words[2]
            elif found:
                if keyword in members:
                    f.seek(pos)
                    param = members[keyword]
                    param = type(param).load(f, **asdict(param.spec))
                    params[keyword] = param
            elif keyword == "end":
                break

        return cls(name, index, **params)

    def write(self, f):
        pass


class MFBlocks(MutableMapping, metaclass=MFBlockMappingMeta):
    def __init__(self, *args, **kwargs):
        self.blocks = dict()
        self.update(dict(*args, **kwargs))

    def __getitem__(self, key):
        return self.blocks[key]

    def __setitem__(self, key, value):
        self.blocks[key] = value

    def __delitem__(self, key):
        del self.blocks[key]

    def __iter__(self):
        return iter(self.blocks)

    def __len__(self):
        return len(self.blocks)

    @classmethod
    def load(cls, f):
        pass

    def write(self, f):
        pass
