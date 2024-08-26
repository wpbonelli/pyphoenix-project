from enum import Enum
from typing import Literal, NamedTuple

InOut = Literal["filein", "fileout"]


class Tags(NamedTuple):
    begin: str = "begin"
    end: str = "end"


class ArrayHow(Enum):
    """
    How a MODFLOW 6 input array is represented in an input file.
    """

    internal = "internal"
    constant = "constant"
    external = "open/close"

    @classmethod
    def from_string(cls, string):
        for e in ArrayHow:
            if string.lower() == e.value:
                return e


class Reader(Enum):
    """
    MODFLOW 6 procedure with which to read input.
    """

    urword = "urword"
    u1ddbl = "u1dbl"
    readarray = "readarray"

    @classmethod
    def from_string(cls, value):
        for e in cls:
            if value.lower() == e.value:
                return e
