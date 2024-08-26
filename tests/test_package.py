from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
from attrs import Factory, define

from flopy4.array import Array
from flopy4.component import Context
from flopy4.mf6.block import Block
from flopy4.param import Choice, Record, param
from flopy4.table import Table


@define(auto_attribs=False)
class TestRecord(Record):
    __test__ = False  # tell pytest not to collect
    _record_keyword: bool = param(
        block="period", description="keyword in record"
    )
    _record_integer: int = param(
        block="period", description="integer in record"
    )


@define(auto_attribs=False)
class TestChoice(Choice):
    __test__ = False  # tell pytest not to collect
    _choice_keyword: bool = param(
        block="period", description="keyword in keystring"
    )
    _choice_record: TestRecord = param(
        block="period",
        description="record in keystring",
        default=Factory(TestRecord),
    )


@define(auto_attribs=False)
class TestComponent(Context):
    __test__ = False  # tell pytest not to collect
    _bool: bool = param(description="keyword")
    _int: int = param(description="integer")
    _float: float = param(description="double")
    _str: str = param(description="string")
    _path: Path = param(description="filename")
    _record: TestRecord = param(
        description="record", default=Factory(TestRecord)
    )
    _choice: TestChoice = param(
        description="discriminated union", default=True
    )
    _choice_list: List[TestChoice] = param(
        description="list of choices", default=Factory(list)
    )
    _array: Array = param(
        description="array parameter", default=Factory(np.zeros((3,)))
    )
    _table: Table = param(
        description="list parameter (occupies its own block)",
        default=Factory(
            lambda: pd.DataFrame(
                np.empty(
                    0,
                    dtype=np.dtype([("a", str), ("b", int), ("c", float)]),
                )
            )
        ),
    )


def test_member_params():
    params = TestComponent.params
    assert len(params) == 6

    k = params["keyword"]
    assert k.metadata["block"] == "options"
    assert k.metadata["description"] == "keyword"
    assert k.metadata["optional"]

    i = params["integer"]
    assert i.metadata["block"] == "options"
    assert i.metadata["description"] == "int"
    assert i.metadata["optional"]

    d = params["double"]
    assert d.metadata["block"] == "options"
    assert d.metadata["description"] == "double"
    assert d.metadata["optional"]

    s = params["string"]
    assert s.metadata["block"] == "options"
    assert s.metadata["description"] == "string"
    assert s.metadata["optional"]

    f = params["file"]
    assert f.metadata["block"] == "options"
    assert f.metadata["description"] == "filename"
    assert f.metadata["optional"]

    a = params["a"]
    assert a.metadata["block"] == "packagedata"
    assert a.metadata["description"] == "array"
    assert a.metadata["optional"]


def test_member_blocks():
    blocks = TestComponent.blocks
    assert len(blocks) == 2

    block = blocks.options
    assert isinstance(block, Block)
    assert len(block.params) == 5

    k = block["k"]
    assert k.description == "keyword"
    assert k.metadata["optional"]

    i = block["i"]
    assert i.description == "int"
    assert i.metadata["optional"]

    d = block["d"]
    assert d.description == "double"
    assert d.metadata["optional"]

    s = block["s"]
    assert s.description == "string"
    assert s.metadata["optional"]

    f = block["f"]
    assert f.description == "filename"
    assert f.metadata["optional"]

    block = blocks.packagedata
    assert isinstance(block, Block)
    assert len(block.params) == 1

    a = block["a"]
    assert a.metadata["description"] == "array"


def test_load_write(tmp_path):
    name = "test"
    fpth = tmp_path / f"{name}.txt"
    array = " ".join(str(x) for x in [1.0, 2.0, 3.0])
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  K\n")
        f.write("  I 1\n")
        f.write("  D 1.0\n")
        f.write("  S value\n")
        f.write(f"  F FILEIN {fpth}\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN PACKAGEDATA\n")
        f.write(f"  A\nINTERNAL\n{array}\n")
        f.write("END PACKAGEDATA\n")

    # test package load
    with open(fpth, "r") as f:
        package = TestComponent.load(f)

        # check block and parameter specifications
        assert len(package.blocks) == 2
        assert len(package.params) == 6
        # assert isinstance(TestPackage.k, MFKeyword)
        assert TestComponent.k.name == "k"
        assert TestComponent.k.block == "options"
        assert TestComponent.k.description == "keyword"

        # check parameter values
        assert isinstance(package.k, bool)
        assert package.k
        assert package.i == 1
        assert package.d == 1.0
        assert package.s == "value"
        assert package.f == fpth

    # test package write
    fpth2 = tmp_path / f"{name}2.txt"
    with open(fpth2, "w") as f:
        package.write(f)
    with open(fpth2, "r") as f:
        lines = f.readlines()
        assert "BEGIN OPTIONS \n" in lines
        assert "  K\n" in lines
        assert "  I 1\n" in lines
        assert "  D 1.0\n" in lines
        assert "  S value\n" in lines
        assert f"  F FILEIN {fpth}\n" in lines
        assert "  A\n" in lines
        assert "    INTERNAL\n" in lines
        assert f"      {array}\n" in lines
        assert "END OPTIONS\n" in lines
