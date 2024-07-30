import numpy as np

from flopy4.array import MFArray
from flopy4.block import MFBlock
from flopy4.idm.gwfdis import GwfDis
from flopy4.idm.gwfic import GwfIc
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class TestPackage(MFPackage):
    __test__ = False  # tell pytest not to collect

    k = MFKeyword(
        block="options",
        description="keyword",
    )
    i = MFInteger(
        block="options",
        description="int",
    )
    d = MFDouble(
        block="options",
        description="double",
    )
    s = MFString(block="options", description="string", optional=False)
    f = MFFilename(block="options", description="filename", optional=False)
    a = MFArray(block="packagedata", description="array", shape=(3))


def test_member_params():
    params = TestPackage.params
    assert len(params) == 6

    k = params.k
    assert isinstance(k, MFKeyword)
    assert k.block == "options"
    assert k.description == "keyword"
    assert k.optional

    i = params.i
    assert isinstance(i, MFInteger)
    assert i.block == "options"
    assert i.description == "int"
    assert i.optional

    d = params.d
    assert isinstance(d, MFDouble)
    assert d.block == "options"
    assert d.description == "double"
    assert d.optional

    s = params.s
    assert isinstance(s, MFString)
    assert s.block == "options"
    assert s.description == "string"
    assert not s.optional

    f = params.f
    assert isinstance(f, MFFilename)
    assert f.block == "options"
    assert f.description == "filename"
    assert not f.optional

    a = params.a
    assert isinstance(a, MFArray)
    assert a.block == "packagedata"
    assert a.description == "array"


def test_member_blocks():
    blocks = TestPackage.blocks
    assert len(blocks) == 2

    block = blocks.options
    assert isinstance(block, MFBlock)
    assert len(block.params) == 5

    k = block["k"]
    assert isinstance(k, MFKeyword)
    assert k.description == "keyword"
    assert k.optional

    i = block["i"]
    assert isinstance(i, MFInteger)
    assert i.description == "int"
    assert i.optional

    d = block["d"]
    assert isinstance(d, MFDouble)
    assert d.description == "double"
    assert d.optional

    s = block["s"]
    assert isinstance(s, MFString)
    assert s.description == "string"
    assert not s.optional

    f = block["f"]
    assert isinstance(f, MFFilename)
    assert f.description == "filename"
    assert not f.optional

    block = blocks.packagedata
    assert isinstance(block, MFBlock)
    assert len(block.params) == 1

    a = block["a"]
    assert isinstance(a, MFArray)
    assert a.description == "array"


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
        package = TestPackage.load(f)

        # check block and parameter specifications
        assert len(package.blocks) == 2
        assert len(package.params) == 6
        assert isinstance(TestPackage.k, MFKeyword)
        assert TestPackage.k.name == "k"
        assert TestPackage.k.block == "options"
        assert TestPackage.k.description == "keyword"

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


def test_loadfail_gwfic(tmp_path):
    name = "gwf"
    fpth = tmp_path / f"{name}.ic"
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  NOT_AN_OPTION\n")
        f.write("END OPTIONS\n")

    # test package load
    with open(fpth, "r") as f:
        try:
            GwfIc.load(f)
        except ValueError as e:
            assert "not_an_option" in str(e)


def test_load_gwfic(tmp_path):
    name = "gwf"
    fpth = tmp_path / f"{name}.ic"
    strt = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
    array = " ".join(str(x) for x in strt)
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  EXPORT_ARRAY_ASCII\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN GRIDDATA\n")
        f.write(f"  STRT\n    INTERNAL\n      {array}\n")
        f.write("END GRIDDATA\n")

    # test package load
    with open(fpth, "r") as f:
        gwfic = GwfIc.load(f)

    assert len(GwfIc.blocks) == len(gwfic.blocks) == 2
    assert len(GwfIc.params) == len(gwfic.params) == 3

    # instance attributes: shortcut access to param values
    assert isinstance(gwfic.export_array_ascii, bool)
    assert isinstance(gwfic.export_array_netcdf, bool)
    assert isinstance(gwfic.strt, np.ndarray)

    assert gwfic.export_array_ascii
    assert not gwfic.export_array_netcdf
    assert np.allclose(gwfic.strt, np.array(strt))


def test_load_gwfdis(tmp_path):
    name = "gwf"
    fpth = tmp_path / f"{name}.dis"
    celld = [1.0, 2.0, 3.0, 4.0, 5.0]
    spacing = " ".join(str(x) for x in celld)
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  EXPORT_ARRAY_ASCII\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN DIMENSIONS\n")
        f.write("  NLAY 3\n")
        f.write("  NROW 5\n")
        f.write("  NCOL 5\n")
        f.write("END DIMENSIONS\n\n")
        f.write("BEGIN GRIDDATA\n")
        f.write(f"  DELR\n    INTERNAL\n      {spacing}\n")
        f.write(f"  DELC\n    INTERNAL\n      {spacing}\n")
        f.write("  TOP\n     CONSTANT 4.0\n")
        f.write("  BOTM LAYERED\n")
        f.write("      CONSTANT 3.0\n")
        f.write("      CONSTANT 2.0\n")
        f.write("      CONSTANT 1.0\n")
        f.write("  IDOMAIN LAYERED\n")
        f.write("    INTERNAL  FACTOR  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  0  1  1\n")
        f.write("      1  1  0  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("    INTERNAL  FACTOR  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("    INTERNAL  FACTOR  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("END GRIDDATA\n")

        # test package load
    with open(fpth, "r") as f:
        gwfdis = GwfDis.load(f)

    assert len(gwfdis.blocks) == 3
    assert len(gwfdis.params) == 9

    # instance attributes: shortcut access to param values
    assert isinstance(gwfdis.export_array_ascii, bool)
    assert isinstance(gwfdis.nlay, int)
    assert isinstance(gwfdis.nrow, int)
    assert isinstance(gwfdis.ncol, int)
    assert isinstance(gwfdis.delr, np.ndarray)
    assert isinstance(gwfdis.delc, np.ndarray)
    assert isinstance(gwfdis.top, np.ndarray)
    assert isinstance(gwfdis.botm, np.ndarray)

    assert gwfdis.export_array_ascii
    assert gwfdis.nlay == 3
    assert gwfdis.nrow == 5
    assert gwfdis.ncol == 5
    assert np.allclose(gwfdis.delr, np.array(celld))
    assert np.allclose(gwfdis.delc, np.array(celld))
    assert np.allclose(gwfdis.top, np.ones((5, 5)) * 4.0)
    # botm
    b = np.ones((3, 5, 5))
    b[0, :, :] = 3.0
    b[1, :, :] = 2.0
    b[2, :, :] = 1.0
    assert np.allclose(gwfdis.botm, b)
    # idomain
    i = np.ones((3, 5, 5))
    i[0, :, :] = [
        [1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1],
        [1, 1, 0, 1, 1],
        [1, 1, 0, 1, 1],
        [1, 1, 1, 1, 1],
    ]
    assert np.allclose(gwfdis.idomain, i)
