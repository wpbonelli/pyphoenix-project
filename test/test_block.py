from flopy4.array import MFArray
from flopy4.block import MFBlock, MFBlocks, get_member_params
from flopy4.list import MFList
from flopy4.scalar import MFKeyword, MFInteger, MFDouble, MFString, MFFilename


class TestBlock(MFBlock):
    __test__ = False # tell pytest not to collect

    k = MFKeyword(description="keyword")
    i = MFInteger(description="int")
    d = MFDouble(description="double")
    s = MFString(description="string")
    f = MFFilename(description="filename", optional=True)
    # a = MFArray(description="array")
    # l = MFList(description="list")


def test_get_member_params():
    params = get_member_params(TestBlock)
    assert len(params) == 5

    k = params["k"]
    assert isinstance(k, MFKeyword)
    assert k.description == "keyword"
    assert not k.optional

    i = params["i"]
    assert isinstance(i, MFInteger)
    assert i.description == "int"
    assert not i.optional

    d = params["d"]
    assert isinstance(d, MFDouble)
    assert d.description == "double"
    assert not d.optional

    s = params["s"]
    assert isinstance(s, MFString)
    assert s.description == "string"
    assert s.optional

    f = params["f"]
    assert isinstance(f, MFFilename)
    assert f.description == "filename"
    assert f.optional

    # a = params["a"]
    # assert isinstance(f, MFArray)
    # assert f.description == "array"
    # assert not f.optional

    # l = params["l"]
    # assert isinstance(f, MFList)
    # assert f.description == "list"
    # assert not f.optional


def test_block_load_no_index(tmp_path):
    name = "options"
    fpth = tmp_path / f"{name}.txt"
    with open(fpth, "w") as f:
        f.write(f"BEGIN {name.upper()}\n")
        f.write(f"  K\n")
        f.write(f"  I 1\n")
        f.write(f"  D 1.0\n")
        f.write(f"  S value\n")
        f.write(f"  F {fpth}\n")
        f.write(f"END {name.upper()}\n")

    with open(fpth, "r") as f:
        block = TestBlock.load(f)
        assert block.k
        assert block.i == 1
        assert block.d == 1.
        assert block.s == "value"
        assert block.f == fpth


def test_block_load_with_index(tmp_path):
    pass


def test_blocks_load(tmp_path):
    pass