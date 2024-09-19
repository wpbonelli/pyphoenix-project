from pathlib import Path

from spec.make_toml import Dfn2Toml


PROJ_ROOT = Path(__file__).parents[1]
DFNS_PATH = PROJ_ROOT / "spec" / "dfn"
TOML_PATH = PROJ_ROOT / "spec" / "toml"


def test_dfn2toml(tmp_path):
    dfn_path = DFNS_PATH / "gwf-ic.dfn"
    Dfn2Toml(dfn_path, tmp_path)
    toml_path = tmp_path / "gwf-ic.toml"
    assert toml_path.is_file()