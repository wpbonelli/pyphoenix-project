from pathlib import Path

from flopy4.dfn import DFN

PROJ_ROOT_PATH = Path(__file__).parents[1]
MODULE_PATH = PROJ_ROOT_PATH / "flopy4"
DFNS_PATH = MODULE_PATH / "dfn"


def test_load():
    dfn_path = DFNS_PATH / "prt-prp.dfn"
    with open(dfn_path, "r") as f:
        dfn = DFN.load(f)
        assert dfn["component"] == "prt"
        assert dfn["subcomponent"] == "prp"
        assert dfn["base_class"] == "MFPackage"
        assert len(dfn["params"]) == 41
