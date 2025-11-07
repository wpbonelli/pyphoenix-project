from pathlib import Path
from typing import Literal, NamedTuple, Optional

import attrs
import numpy as np
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.utils import to_path


@attrs.define(slots=False)
class All:
    all: Literal["all"] = "all"

@attrs.define(slots=False)
class First:
    first: Literal["first"] = "first"

@attrs.define(slots=False)
class Last:
    last: Literal["last"] = "last"

@attrs.define(slots=False)
class Steps:
    steps: tuple[int, ...] = (1,)

@attrs.define(slots=False)
class Frequency:
    frequency: int = 1


@xattree
class Oc(Package):
    @attrs.define(slots=False)
    class Format:
        fmt_kw: str = attrs.field(default="print_format")
        columns: int = attrs.field(default=10)
        width: int = attrs.field(default=11)
        digits: int = attrs.field(default=4)
        format: Literal["exponential", "fixed", "general", "scientific"] = field(default="general")

    @attrs.define(slots=False)
    class PrintSaveSetting:
        saverecord: list["Oc.SaveRecord"] = attrs.field(default=list)
        printrecord: list["Oc.PrintRecord"] = attrs.field(default=list)

    @attrs.define(slots=False)
    class SaveRecord:
        save: Literal["save"] = attrs.field(init=False, default="save")
        rtype: str = attrs.field()
        steps: All | First | Last | Steps | Frequency = attrs.field()

    @attrs.define(slots=False)
    class PrintRecord:
        print: Literal["print"] = attrs.field(init=False, default="print")
        rtype: str = attrs.field()
        steps: All | First | Last | Steps | Frequency = attrs.field()

    @attrs.define(slots=False)
    class Steps:
        all: bool | None = attrs.field(default=None)
        first: bool | None = attrs.field(default=None)
        last: bool | None = attrs.field(default=None)
        steps: tuple[int, ...] | None = attrs.field(default=None)
        frequency: int | None = attrs.field(default=None)

    # class Steps(NamedTuple):
    #     all: bool | None = True
    #     first: bool | None = None
    #     last: bool | None = None
    #     steps: tuple[int, ...] | None = None
    #     frequency: int | None = None

    


    budget_file: Optional[Path] = path(
        block="options", converter=to_path, default=None, inout="fileout"
    )
    budget_csv_file: Optional[Path] = path(
        block="options", converter=to_path, default=None, inout="fileout"
    )
    head_file: Optional[Path] = path(
        block="options", converter=to_path, default=None, inout="fileout"
    )
    # TODO: needs converter and then rename?
    head: Optional[Format] = field(block="options", default=None)
    save_head: Optional[NDArray[np.str_]] = array(
        dtype=np.dtypes.StringDType(),
        block="period",
        default=None,
        dims=("nper",),
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
    )
    save_budget: Optional[NDArray[np.str_]] = array(
        dtype=np.dtypes.StringDType(),
        block="period",
        default=None,
        dims=("nper",),
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
    )
    print_head: Optional[NDArray[np.str_]] = array(
        dtype=np.dtypes.StringDType(),
        block="period",
        default=None,
        dims=("nper",),
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
    )
    print_budget: Optional[NDArray[np.str_]] = array(
        dtype=np.dtypes.StringDType(),
        block="period",
        default=None,
        dims=("nper",),
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
    )
    perioddata: Optional[NDArray[np.object_]] = array(
        dtype=PrintSaveSetting,
        block="period",
        default=None,
        dims=("nper",),
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
    )
