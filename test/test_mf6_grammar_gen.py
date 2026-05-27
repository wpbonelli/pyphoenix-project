import pytest
from modflow_devtools.dfns import Dfns, Double, Keyword, Package
from packaging.version import Version

from flopy4.mf6.codec.reader.grammar import make_grammar, make_grammars


@pytest.fixture
def minimal_dfn():
    return Package(
        schema_version=Version("2.0.0"),
        name="test-component",
        blocks={
            "options": {
                "test_field": Keyword(
                    name="test_field",
                )
            }
        },
    )


@pytest.fixture
def simple_dfn():
    return Package(
        schema_version=Version("2.0.0"),
        name="gwf-test",
        blocks={
            "options": {
                "export_ascii": Keyword(
                    name="export_array_ascii",
                    block="options",
                )
            },
            "griddata": {
                "strt": Double(
                    name="strt",
                    block="griddata",
                    shape=["nodes"],
                )
            },
        },
    )


def test_make_grammar(tmp_path, minimal_dfn):
    make_grammar(minimal_dfn, tmp_path)

    expected_file = tmp_path / "test-component.lark"
    assert expected_file.exists()
    assert expected_file.is_file()
    content = expected_file.read_text()
    assert "// Auto-generated grammar for MF6 TEST-COMPONENT" in content
    assert "%import typed.integer -> integer" in content
    assert "%import typed.double -> double" in content
    assert "start: block*" in content
    assert "options_block" in content

    make_grammar(simple_dfn, tmp_path)

    grammar_file = tmp_path / "gwf-test.lark"
    content = grammar_file.read_text()

    assert "options_block" in content
    assert "griddata_block" in content
    assert 'begin"i "options"' in content.lower()
    assert 'begin"i "griddata"' in content.lower()
    assert "strt" in content
    assert "array" in content.lower()


def test_make_all_grammars(tmp_path):
    outdir = tmp_path / "new_directory"
    assert not outdir.exists()

    dfns = {
        "test1": Package(
            schema_version="2.0.0",
            name="test1",
            blocks={},
        )
    }

    make_grammars(dfns, outdir)
    assert outdir.exists()
    assert outdir.is_dir()

    Dfns(
        {
            "comp1": Package(
                schema_version="2.0.0",
                name="comp1",
                blocks={},
            ),
            "comp2": Package(
                schema_version="2.0.0",
                name="comp2",
                blocks={},
            ),
            "comp3": Package(
                schema_version="2.0.0",
                name="comp3",
                blocks={},
            ),
        }
    )

    make_grammars(dfns, tmp_path)

    assert (tmp_path / "comp1.lark").exists()
    assert (tmp_path / "comp2.lark").exists()
    assert (tmp_path / "comp3.lark").exists()


def test_make_grammars_empty(tmp_path):
    make_grammars({}, tmp_path)

    assert tmp_path.exists()
    assert len(list(tmp_path.glob("*.lark"))) == 0
