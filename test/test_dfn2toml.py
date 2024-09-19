from conftest import SPEC_PATH

from flopy4.mf6.io.spec.dfn2toml import load_spec

DFNS_PATH = SPEC_PATH / "dfn"


def test_load_spec():
    dfn_paths = DFNS_PATH.glob("*.dfn")
    spec = load_spec(*dfn_paths)
    assert set(spec.keys()) == {
        "gwf",
        "gwt",
        "gwe",
        "prt",
        "sim",
        "exg",
        "sln",
    }
