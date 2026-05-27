"""Test the MF6 input file reader as implemented with lark."""

import os
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from lark import Lark
from modflow_devtools.dfns import Dfns
from modflow_devtools.download import download_and_unzip
from packaging.version import Version

from flopy4.mf6.codec.reader.parser import get_typed_parser
from flopy4.mf6.codec.reader.transformer.typed import TypedTransformer

PROJ_ROOT_PATH = Path(__file__).parents[1]
BASE_GRAMMAR_PATH = (
    PROJ_ROOT_PATH / "flopy4" / "mf6" / "codec" / "reader" / "grammar" / "typed.lark"
)


def typed_parser(grammar: str):
    with open(BASE_GRAMMAR_PATH, "r") as f:
        return Lark(grammar + os.linesep + f.read(), parser="lalr", debug=True)


def test_parse_internal_array():
    parser = typed_parser("start: array")
    tree = parser.parse("""
INTERNAL FACTOR 1.0 IPRN 3
1.2 3.7 9.3 4.2 2.2 9.9 1.0
3.3 4.9 7.3 7.5 8.2 8.7 6.6
4.5 5.7 2.2 1.1 1.7 6.7 6.9
7.4 3.5 7.8 8.5 7.4 6.8 8.8
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    readarray = array.children[0].children[-1]
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    internal = control.children[0]
    assert str(internal.data) == "internal"
    assert len(internal.children) == 2
    factor = internal.children[0]
    assert str(factor.data) == "factor"
    assert str(factor.children[0].data) == "double"
    assert float(factor.children[0].children[0]) == 1.0
    iprn = internal.children[1]
    assert str(iprn.data) == "iprn"
    assert str(iprn.children[0].data) == "integer"
    assert int(iprn.children[0].children[0]) == 3
    data = readarray.children[-1]
    assert len(data.children) == 28
    assert str(data.children[0].data) == "double"
    assert str(data.children[-1].data) == "double"
    assert float(data.children[0].children[0]) == 1.2
    assert float(data.children[-1].children[0]) == 8.8


def test_parse_layered_array():
    parser = typed_parser("start: array")
    tree = parser.parse("""
LAYERED
CONSTANT 1.0
INTERNAL FACTOR 1.0 IPRN 3
1.2 3.7 9.3 4.2 2.2 9.9 1.0
3.3 4.9 7.3 7.5 8.2 8.7 6.6
4.5 5.7 2.2 1.1 1.7 6.7 6.9
7.4 3.5 7.8 8.5 7.4 6.8 8.8
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    layered_array = array.children[0]
    assert str(layered_array.data) == "layered_array"
    assert len(layered_array.children) == 4  # 2nd item is optional netcdf
    layered = layered_array.children[0]
    assert str(layered.data) == "layered"
    layer1 = layered_array.children[-2]
    assert str(layer1.data) == "readarray"
    control1 = layer1.children[0]
    assert str(control1.data) == "control"
    constant = control1.children[0]
    assert str(constant.data) == "constant"
    assert str(constant.children[0].data) == "double"
    assert float(constant.children[0].children[0]) == 1.0
    layer2 = layered_array.children[-1]
    assert str(layer2.data) == "readarray"
    control2 = layer2.children[0]
    assert str(control2.data) == "control"
    internal = control2.children[0]
    assert str(internal.data) == "internal"
    factor = internal.children[0]
    assert str(factor.data) == "factor"
    assert float(factor.children[0].children[0]) == 1.0
    iprn = internal.children[1]
    assert str(iprn.data) == "iprn"
    assert int(iprn.children[0].children[0]) == 3
    data = layer2.children[1]
    assert len(data.children) == 28
    assert float(data.children[0].children[0]) == 1.2
    assert float(data.children[-1].children[0]) == 8.8


def test_parse_constant_array():
    parser = typed_parser("start: array")
    tree = parser.parse("""
CONSTANT 1.0
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    single_array = array.children[0]
    assert str(single_array.data) == "single_array"
    readarray = single_array.children[-1]  # optional netcdf comes first
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    constant = control.children[0]
    assert str(constant.data) == "constant"
    assert str(constant.children[0].data) == "double"
    assert float(constant.children[0].children[0]) == 1.0


def test_parse_external_array_no_quotation_marks():
    parser = typed_parser("start: array")
    tree = parser.parse("""
OPEN/CLOSE some.file
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    single_array = array.children[0]
    assert str(single_array.data) == "single_array"
    readarray = single_array.children[-1]  # optional netcdf comes first
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    external = control.children[0]
    assert str(external.data) == "external"
    filename = external.children[0]
    assert str(filename.data) == "filename"
    # there's an intermediate "word",
    # TODO any way to get rid of it?
    assert str(filename.children[0].children[0]) == "some.file"


def test_parse_external_array_with_quotation_marks():
    parser = typed_parser("start: array")
    tree = parser.parse("""
OPEN/CLOSE "some.file"
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    single_array = array.children[0]
    assert str(single_array.data) == "single_array"
    readarray = single_array.children[-1]
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    external = control.children[0]
    assert str(external.data) == "external"
    filename = external.children[0]
    assert str(filename.data) == "filename"
    assert str(filename.children[0]) == '"some.file"'


def test_transform_internal_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
INTERNAL FACTOR 1.5 IPRN 3
1.2 3.7 9.3 4.2
2.2 9.9 1.0 3.3
4.9 7.3 7.5 8.2
8.7 6.6 4.5 5.7
    """)
    )
    assert result["control"]["type"] == "internal"
    assert result["control"]["factor"] == 1.5
    assert result["control"]["iprn"] == 3
    assert result["data"].shape == (16,)


def test_transform_constant_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
CONSTANT 42.5
    """)
    )
    assert result["control"]["type"] == "constant"
    assert np.array_equal(result["data"], np.array(42.5))


def test_transform_external_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
OPEN/CLOSE "data/heads.dat" FACTOR 1.0 (BINARY)
    """)
    )
    assert result["control"]["type"] == "external"
    assert result["data"] == Path("data/heads.dat")


def test_transform_layered_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
LAYERED
CONSTANT 1.0
INTERNAL FACTOR 2.0
1.2 3.7 9.3 4.2
2.2 9.9 1.0 3.3
    """)
    )
    assert isinstance(result["control"], list)
    assert result["control"][0]["type"] == "constant"
    assert result["control"][1]["type"] == "internal"
    assert result["control"][1]["factor"] == 2.0
    assert isinstance(result["data"], xr.DataArray)
    assert result["data"].shape == (2, 8)
    assert result["data"].dims == ("layer", "dim_0")
    assert np.array_equal(result["data"][0], np.ones((8,)))


def test_transform_full_component():
    dfn = Dfn.from_dict(
        {
            "name": "test_transform",
            "schema_version": Version("2"),
            "blocks": {
                "options": {
                    "r2d2": {"name": "r2d2", "type": "keyword"},
                    "b": {"name": "b", "type": "string"},
                    "c": {"name": "c", "type": "integer"},
                    "p": {"name": "p", "type": "double"},
                },
                "arrays": {
                    "x": {"name": "x", "type": "double", "shape": None},
                    "y": {"name": "y", "type": "array", "shape": None},
                    "z": {"name": "z", "type": "array", "shape": None},
                },
            },
        }
    )
    grammar = """
start: block*
block: options_block | arrays_block
options_block: "begin"i "options"i options_fields "end"i "options"i
arrays_block: "begin"i "arrays"i arrays_fields "end"i "arrays"i
options_fields: (r2d2 | b | c | p)*
arrays_fields: (x | y | z)*
r2d2: "r2d2"i // keyword
b: "b"i string
c: "c"i integer
p: "p"i double
x: "x"i array
y: "y"i array
z: "z"i array
"""
    parser = typed_parser(grammar)
    transformer = TypedTransformer(dfn=dfn)
    result = transformer.transform(
        parser.parse("""
BEGIN OPTIONS
    R2D2
    B "nice said"
    C 3
    P 0.
END OPTIONS
BEGIN ARRAYS
    X CONSTANT 1.0
    Y INTERNAL 4.0 5.0 6.0
    Z OPEN/CLOSE "data/z.dat" FACTOR 1.0 (BINARY)
END ARRAYS
""")
    )
    assert "options" in result
    assert "arrays" in result
    assert result["options"]["r2d2"] is True
    assert result["options"]["b"] == "nice said"
    assert result["options"]["c"] == 3
    assert result["options"]["p"] == 0.0
    assert result["arrays"]["x"]["control"]["type"] == "constant"
    assert np.array_equal(result["arrays"]["x"]["data"], np.array(1.0))
    assert result["arrays"]["y"]["control"]["type"] == "internal"
    assert np.array_equal(result["arrays"]["y"]["data"], np.array([4.0, 5.0, 6.0]))
    assert result["arrays"]["z"]["control"]["type"] == "external"
    assert result["arrays"]["z"]["control"]["factor"] == 1.0
    assert result["arrays"]["z"]["control"]["binary"] is True
    assert result["arrays"]["z"]["data"] == Path("data/z.dat")


MF6_EXAMPLES_URL = (
    "https://github.com/MODFLOW-ORG/modflow6-examples/releases/download/current/mf6examples.zip"
)


@pytest.fixture(scope="session")
def mf6_examples_path(tmp_path_factory):
    """Download and cache MF6 example models for the test session."""
    tmp_dir = tmp_path_factory.mktemp("mf6_examples")
    download_and_unzip(MF6_EXAMPLES_URL, tmp_dir, verbose=False)
    return tmp_dir


@pytest.fixture
def model_workspace(mf6_examples_path, request):
    model_name = request.param
    dir_name = model_name.split("/")[-1]
    workspace = mf6_examples_path / dir_name
    if not workspace.is_dir():
        pytest.skip(f"Model directory '{dir_name}' not found")
    return workspace


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-bcf2ss-p01a"], indirect=True)
def test_transform_gwf_oc_file(model_workspace, dfn_path):

    dfns = Dfns.load(dfn_path)
    dfn = dfn["gwf-oc"]

    oc_file = next(iter(model_workspace.rglob("*.oc")), None)
    assert oc_file

    parser = get_typed_parser("gwf-oc")
    transformer = TypedTransformer(dfn=dfn)

    with open(oc_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    assert isinstance(result, dict)
    assert "options" in result
    options = result["options"]
    assert "budget_filerecord" in options
    assert options["budget_filerecord"]["budgetfile"] == "ex-gwf-bcf2ss.cbc"
    assert "head_filerecord" in options
    assert options["head_filerecord"]["headfile"] == "ex-gwf-bcf2ss.hds"
    assert "period 1" in result
    period_data = result["period 1"]
    assert "saverecord" in period_data
    save_records = period_data["saverecord"]
    assert len(save_records) == 2
    rtypes = [rec["rtype"] for rec in save_records]
    assert "HEAD" in rtypes
    assert "BUDGET" in rtypes
    for rec in save_records:
        assert "ocsetting" in rec
        assert rec["ocsetting"] == "all"


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_dis_file(model_workspace, dfn_path):
    dfns = Dfns.load(dfn_path)
    dfn = dfns["gwf-dis"]

    dis_file = next(iter((model_workspace.rglob("*.dis"))), None)
    assert dis_file

    parser = get_typed_parser("gwf-dis")
    transformer = TypedTransformer(dfn=dfn)

    with open(dis_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    assert isinstance(result, dict)
    assert "dimensions" in result
    assert "nlay" in result["dimensions"]
    assert "nrow" in result["dimensions"]
    assert "ncol" in result["dimensions"]
    assert result["dimensions"]["nlay"] > 0
    assert result["dimensions"]["nrow"] > 0
    assert result["dimensions"]["ncol"] > 0
    assert "griddata" in result
    griddata = result["griddata"]
    assert "delr" in griddata
    assert "delc" in griddata
    assert "top" in griddata
    assert "botm" in griddata
    assert "control" in griddata["delr"]
    assert "data" in griddata["delr"]


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_npf_file(model_workspace, dfn_path):
    dfns = Dfns.load(dfn_path)
    dfn = dfns["gwf-npf"]

    npf_file = next(iter((model_workspace.rglob("*.npf"))), None)
    assert npf_file

    parser = get_typed_parser(dfn=dfn)
    transformer = TypedTransformer(dfn=dfn)

    with open(npf_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    assert isinstance(result, dict)
    assert "options" in result
    options = result["options"]
    assert "save_specific_discharge" in options
    assert options["save_specific_discharge"] is True
    assert "griddata" in result
    griddata = result["griddata"]
    assert "icelltype" in griddata
    assert "k" in griddata
    assert "control" in griddata["icelltype"]
    assert "data" in griddata["icelltype"]
    assert "control" in griddata["k"]
    assert "data" in griddata["k"]


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_sto_file(model_workspace, dfn_path):
    dfns = Dfns.load(dfn_path)
    dfn = dfns.components["gwf-sto"]

    sto_file = next(iter(model_workspace.rglob("*.sto")), None)
    assert sto_file

    parser = get_typed_parser(dfn)
    transformer = TypedTransformer(dfn=dfn)

    with open(sto_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    assert isinstance(result, dict)
    assert "griddata" in result
    griddata = result["griddata"]
    assert "iconvert" in griddata
    assert "control" in griddata["iconvert"]
    assert "data" in griddata["iconvert"]
