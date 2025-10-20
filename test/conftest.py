from pathlib import Path

import pytest

pytest_plugins = ["modflow_devtools.fixtures"]

PROJ_ROOT_PATH = Path(__file__).parents[1]
TEST_PATH = PROJ_ROOT_PATH / "test"
DOCS_PATH = PROJ_ROOT_PATH / "docs"
EXAMPLES_PATH = DOCS_PATH / "examples"
EXCLUDED_EXAMPLES = []


@pytest.fixture
def test_data_path() -> Path:
    return TEST_PATH / "data"


def pytest_generate_tests(metafunc):
    if "example_script" in metafunc.fixturenames:
        scripts = {
            file.name: file
            for file in sorted(EXAMPLES_PATH.glob("*example.py"))
            if file.stem not in EXCLUDED_EXAMPLES
        }
        metafunc.parametrize("example_script", scripts.values(), ids=scripts.keys())
