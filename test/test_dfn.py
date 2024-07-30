from pathlib import Path

from conftest import PROJ_ROOT_PATH

from flopy4.dfn import DFN, DFNs


def test_dfn_load():
    key = "prt-prp"

    fpth = Path(PROJ_ROOT_PATH / "spec" / "dfn" / f"{key}.dfn")
    with open(fpth, "r") as f:
        dfn = DFN.load(f)

    assert dfn.component == "prt"
    assert dfn.subcomponent == "prp"
    assert type(dfn.data) is dict
    assert len(dfn) == 41
    assert list(dfn.blocks.keys()) == [
        "options",
        "dimensions",
        "packagedata",
        "period",
    ]

    for b in dfn.blocks.keys():
        block_d = dfn[b]
        assert type(block_d) is dict

    assert list(dfn.keys()) == [
        "boundnames",
        "print_input",
        "dev_exit_solve_method",
        "exit_solve_tolerance",
        "local_z",
        "extend_tracking",
        "track_filerecord",
        "track",
        "fileout",
        "trackfile",
        "trackcsv_filerecord",
        "trackcsv",
        "trackcsvfile",
        "stoptime",
        "stoptraveltime",
        "stop_at_weak_sink",
        "istopzone",
        "drape",
        "release_timesrecord",
        "release_times",
        "times",
        "release_timesfilerecord",
        "release_timesfile",
        "timesfile",
        "dev_forceternary",
    ]

    assert dfn["drape"] == {
        "type": "keyword",
        "block_variable": False,
        "valid": [],
        "shape": "",
        "tagged": True,
        "in_record": False,
        "layered": False,
        "time_series": False,
        "reader": "urword",
        "optional": True,
        "preserve_case": False,
        "numeric_index": False,
        "longname": "drape",
        "description": "is a text keyword to indicate that if a particle's "
        "release point is in a cell that happens to be inactive at release "
        "time, the particle is to be moved to the topmost active cell below "
        "it, if any. By default, a particle is not released into the "
        "simulation if its release point's cell is inactive at release time.",
        "deprecated": "",
    }


def test_dfns():
    key = "prt-prp"
    fpth = Path(PROJ_ROOT_PATH / "spec" / "dfn" / f"{key}.dfn")
    with open(fpth, "r") as f:
        dfn = DFN.load(f)
    dfns = DFNs({dfn.name: dfn})
    assert len(dfns) == 1

    d = dfns[key]
    assert type(d) is DFN
    assert d is dfn
    assert d.component == "prt"
    assert d.subcomponent == "prp"
    assert dfns.get(key) is d
