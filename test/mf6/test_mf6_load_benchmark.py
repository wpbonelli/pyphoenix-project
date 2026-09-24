"""Simulation load benchmarks: flopy3 (`MFSimulation.load`) vs. flopy4
(basic loader, `Simulation.load`) over the real MF6 corpus.

Opt-in, like the reader benchmarks -- skipped unless benchmarking is
enabled::

    pixi run -e dev bench-load                              # run, autosave
    pixi run -e dev bench-load --benchmark-compare          # vs. last save

There's no typed column: typed `loads` output isn't wired into structuring
yet, so a full typed load doesn't exist. The typed loader is benchmarked at
the parse stage only, in `test_mf6_reader_benchmark.py`.

The loaders don't do the same work by default (details in `load_bench.py`
and docs/dev/load-benchmarks.md): flopy3 defers reading ``OPEN/CLOSE``
arrays until access, and loads packages and child files flopy4 skips. So:

- flopy3 is restricted with ``load_only`` to the package types flopy4
  loaded for that model;
- the corpus is the `KNOWN_PASSING` models where both loaders, after load
  and materialize, open exactly the same set of files. That's checked in a
  subprocess (an audit hook) once per session;
- two stages are timed: ``sim-load`` (load only) and
  ``sim-load-materialize`` (load, then fetch and sum every array and list).
  Only the second is a like-for-like comparison.

Pin the model set with ``--bench-load-manifest PATH``: the first run writes
the list, later runs use exactly that list and fail loudly if a listed model
no longer loads or no longer does equal work. `bench-load` pins it to
`load_bench_models.txt` next to this file.

Warm numbers (in-process, one untimed warm-up round) are the main result.
`test_bench_cold_start` adds a fresh interpreter per round: import, flopy3's
DFN structure / flopy4's grammar build, then load + materialize of one model.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest
from modflow_devtools.models import copy_to

from . import load_bench
from .test_mf6_load_all_models import KNOWN_PASSING

ROUNDS = 3
COLD_ROUNDS = 5
N_LARGEST = 5
# a mid-size DISV model (~0.55 MB, 5 packages + an OPEN/CLOSE array);
# the corpus median is ~12 KB, so "mid" is relative to the models that
# take long enough to measure
COLD_MODEL = "mf6/test/test050_circle_island"
HELPER = Path(load_bench.__file__)


@pytest.fixture(scope="module", autouse=True)
def _require_benchmarking(request):
    config = request.config
    if config.getoption("benchmark_disable") and not config.getoption("benchmark_enable"):
        pytest.skip("benchmarks disabled; pass --benchmark-enable")


class Model(NamedTuple):
    name: str
    ws: Path
    load_only: list[str]
    n_bytes: int


class LoadCorpus(NamedTuple):
    models: list[Model]
    excluded: dict[str, str]  # model -> reason

    @property
    def info(self) -> dict:
        import flopy

        return {
            "n_models": len(self.models),
            "n_bytes": sum(m.n_bytes for m in self.models),
            "n_excluded": len(self.excluded),
            "flopy_version": flopy.__version__,
            "flopy3_options": load_bench.FLOPY3_OPTIONS,
        }


def _exclusion_reason(result: dict) -> str:
    if "error" in result:
        return result["error"]
    return f"only flopy3 opens {result['only_flopy3']}; only flopy4 opens {result['only_flopy4']}"


@pytest.fixture(scope="module")
def load_corpus(request, tmp_path_factory) -> LoadCorpus:
    manifest: Path | None = request.config.getoption("bench_load_manifest")
    pinned = manifest.read_text().split() if manifest and manifest.exists() else None
    names = pinned if pinned is not None else sorted(KNOWN_PASSING)

    workspaces = {}
    for name in names:
        ws = copy_to(tmp_path_factory.mktemp("bench-load"), name, verbose=False)
        if ws is not None and (ws / "mfsim.nam").exists():
            workspaces[str(ws)] = (name, ws)
    missing = set(names) - {name for name, _ in workspaces.values()}
    if pinned is not None and missing:
        pytest.fail(f"pinned models not found: {sorted(missing)}")

    # a fresh interpreter, so the audit hook never touches the timed process
    proc = subprocess.run(
        [sys.executable, str(HELPER), "check", *workspaces],
        capture_output=True,
        text=True,
        check=True,
    )
    results = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    assert len(results) == len(workspaces), proc.stderr[-2000:]

    models, excluded = [], {}
    for result in results:
        name, ws = workspaces[result["ws"]]
        if result.get("equal"):
            models.append(Model(name, ws, result["load_only"], result["n_bytes"]))
        else:
            excluded[name] = _exclusion_reason(result)
    if pinned is not None and excluded:
        pytest.fail(f"pinned models no longer load with equal work: {excluded}")
    assert models, "empty load benchmark corpus"
    if pinned is None and manifest is not None:
        manifest.write_text("\n".join(m.name for m in models) + "\n")
    return LoadCorpus(models, excluded)


def _load_flopy3(models: list[Model]) -> None:
    for m in models:
        load_bench.load_flopy3(m.ws, m.load_only)


def _load_flopy4(models: list[Model]) -> None:
    for m in models:
        load_bench.load_flopy4(m.ws)


def _load_materialize_flopy3(models: list[Model]) -> None:
    for m in models:
        load_bench.materialize_flopy3(load_bench.load_flopy3(m.ws, m.load_only))


def _load_materialize_flopy4(models: list[Model]) -> None:
    for m in models:
        load_bench.materialize_flopy4(load_bench.load_flopy4(m.ws))


@pytest.fixture
def quiet():
    import logging
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.disable(logging.CRITICAL)
        try:
            yield
        finally:
            logging.disable(logging.NOTSET)


@pytest.mark.slow
@pytest.mark.parametrize(
    "group, fn",
    [
        ("sim-load", _load_flopy3),
        ("sim-load", _load_flopy4),
        ("sim-load-materialize", _load_materialize_flopy3),
        ("sim-load-materialize", _load_materialize_flopy4),
    ],
    ids=["load-flopy3", "load-flopy4", "load-materialize-flopy3", "load-materialize-flopy4"],
)
def test_bench_corpus(benchmark, load_corpus, quiet, group, fn):
    benchmark.group = group
    benchmark.extra_info.update(load_corpus.info)
    benchmark.pedantic(fn, args=(load_corpus.models,), rounds=ROUNDS, iterations=1, warmup_rounds=1)


@pytest.mark.slow
@pytest.mark.parametrize("loader", ["flopy3", "flopy4"])
@pytest.mark.parametrize("rank", range(1, N_LARGEST + 1), ids=lambda r: f"largest{r}")
def test_bench_largest(benchmark, load_corpus, quiet, rank, loader):
    """Load + materialize of each of the largest corpus models (by input
    bytes), where per-model differences show most."""
    model = sorted(load_corpus.models, key=lambda m: -m.n_bytes)[rank - 1]
    fn = _load_materialize_flopy3 if loader == "flopy3" else _load_materialize_flopy4
    benchmark.group = f"sim-load-materialize-largest{rank}"
    benchmark.extra_info.update(model=model.name, n_bytes=model.n_bytes)
    benchmark.pedantic(fn, args=([model],), rounds=ROUNDS, iterations=1, warmup_rounds=1)


@pytest.mark.slow
@pytest.mark.parametrize("loader", ["flopy3", "flopy4"])
def test_bench_cold_start(benchmark, load_corpus, loader):
    """Wall time of a fresh interpreter that imports `loader`, then loads
    and materializes `COLD_MODEL`. The child's own import/load/materialize
    split (last round) goes in `extra_info`."""
    model = next((m for m in load_corpus.models if m.name == COLD_MODEL), None)
    if model is None:
        pytest.fail(f"{COLD_MODEL} not in the load corpus")
    cmd = [sys.executable, str(HELPER), "cold", loader, str(model.ws)]
    if loader == "flopy3":
        cmd += model.load_only
    split: dict = {}

    def run():
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        split.update(json.loads(proc.stdout.strip().splitlines()[-1]))

    benchmark.group = "sim-load-cold"
    benchmark.extra_info.update(model=model.name, n_bytes=model.n_bytes)
    benchmark.pedantic(run, rounds=COLD_ROUNDS, iterations=1)
    benchmark.extra_info.update(split)
