from pathlib import Path
from pprint import pprint

import toml

from flopy4.mf6.io.spec.make_toml import Dfn2Toml

PROJ_ROOT = Path(__file__).parents[1]
SPEC_PATH = PROJ_ROOT / "flopy4" / "mf6" / "io" / "spec"
DFNS_PATH = SPEC_PATH / "dfn"
TOML_PATH = SPEC_PATH / "toml"


def test_dfn2toml(tmp_path):
    dfn_path = DFNS_PATH / "gwf-ic.dfn"
    Dfn2Toml(dfn_path, tmp_path)
    toml_path = tmp_path / "gwf-ic.toml"
    assert toml_path.is_file()
    dfn = toml.load(toml_path)
    pprint(dfn)
