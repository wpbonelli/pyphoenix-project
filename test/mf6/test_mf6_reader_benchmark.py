"""Reader benchmarks: basic vs. typed loaders over the real MF6 corpus.

Opt-in -- skipped unless benchmarking is enabled (``pytest.ini`` passes
``--benchmark-disable`` by default), e.g.::

    pixi run -e dev bench                                  # run, autosave
    pixi run -e dev bench --benchmark-compare              # vs. last save

The corpus is every package file a `KNOWN_PASSING` model resolves (the
same collection the typed-grammar corpus test uses), narrowed to files
*both* grammars parse as-is -- so basic/typed time identical input.
`n_files`/`n_bytes` are recorded in each benchmark's `extra_info`: when
comparing runs across a grammar change, check they match, since a file
the changed grammar newly rejects silently drops out of the set.

To compare grammar variants on identical input, pin the corpus with
``--bench-manifest PATH``: the first run (on the stricter variant) writes
the file list it used, and later runs use exactly that list, failing
loudly if any listed file no longer parses.

Two stages per loader: ``parse`` (Lark only -- where a lexer/grammar change
shows up) and ``loads`` (parse + transform, the public entry point).
Parser/transformer construction is excluded from both and measured
separately by `test_bench_typed_grammar_build`.
"""

import logging
import warnings
from pathlib import Path
from typing import NamedTuple

import pytest
from modflow_devtools.models import copy_to

from flopy4.mf6.codec.reader import BASIC_PARSER, loads_basic, loads_typed
from flopy4.mf6.codec.reader.parser import get_typed_parser

from .test_mf6_load_all_models import KNOWN_PASSING
from .test_mf6_typed_grammar_corpus import _collect_package_files

ROUNDS = 3


@pytest.fixture(scope="module", autouse=True)
def _require_benchmarking(request):
    config = request.config
    if config.getoption("benchmark_disable") and not config.getoption("benchmark_enable"):
        pytest.skip("benchmarks disabled; pass --benchmark-enable")


class Corpus(NamedTuple):
    files: list[tuple[str, str]]  # (dfn_name, text)
    dfn_path: str

    @property
    def info(self) -> dict:
        return {
            "n_files": len(self.files),
            "n_bytes": sum(len(text) for _, text in self.files),
            "n_components": len({name for name, _ in self.files}),
        }


@pytest.fixture(scope="module")
def corpus(request, tmp_path_factory, dfn_path) -> Corpus:
    dfn_path = str(dfn_path)
    manifest: Path | None = request.config.getoption("bench_manifest")
    pinned = set(manifest.read_text().split()) if manifest and manifest.exists() else None
    files: list[tuple[str, str]] = []
    keys: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.disable(logging.CRITICAL)
        try:
            for model_name in sorted(KNOWN_PASSING):
                workspace = copy_to(tmp_path_factory.mktemp("bench"), model_name, verbose=False)
                sim_path = workspace / "mfsim.nam"
                if not sim_path.exists():
                    continue
                for path, dfn_name in _collect_package_files(sim_path):
                    key = f"{model_name}/{Path(path).relative_to(workspace).as_posix()}"
                    if pinned is not None and key not in pinned:
                        continue
                    text = Path(path).read_text()
                    try:
                        BASIC_PARSER.parse(text)
                        get_typed_parser(dfn_name).parse(text)
                        loads_basic(text)
                        loads_typed(text, dfn_name, dfn_path=dfn_path)
                    except Exception as exc:
                        if pinned is not None:
                            pytest.fail(f"pinned corpus file no longer parses: {key}: {exc!r}")
                        continue
                    files.append((dfn_name, text))
                    keys.append(key)
        finally:
            logging.disable(logging.NOTSET)
    assert files, "empty benchmark corpus"
    if pinned is not None:
        missing = pinned - set(keys)
        assert not missing, f"pinned corpus files not found: {sorted(missing)[:5]}"
    elif manifest is not None:
        manifest.write_text("\n".join(keys) + "\n")
    return Corpus(files, dfn_path)


def _parse_basic(corpus: Corpus) -> None:
    for _, text in corpus.files:
        BASIC_PARSER.parse(text)


def _parse_typed(corpus: Corpus) -> None:
    for name, text in corpus.files:
        get_typed_parser(name).parse(text)


def _loads_basic(corpus: Corpus) -> None:
    for _, text in corpus.files:
        loads_basic(text)


def _loads_typed(corpus: Corpus) -> None:
    for name, text in corpus.files:
        loads_typed(text, name, dfn_path=corpus.dfn_path)


@pytest.mark.slow
@pytest.mark.parametrize(
    "stage, loader, fn",
    [
        ("parse", "basic", _parse_basic),
        ("parse", "typed", _parse_typed),
        ("loads", "basic", _loads_basic),
        ("loads", "typed", _loads_typed),
    ],
    ids=["parse-basic", "parse-typed", "loads-basic", "loads-typed"],
)
def test_bench_corpus(benchmark, corpus, stage, loader, fn):
    benchmark.group = f"corpus-{stage}"
    benchmark.extra_info.update(corpus.info)
    benchmark.pedantic(fn, args=(corpus,), rounds=ROUNDS, iterations=1)


@pytest.mark.slow
def test_bench_typed_grammar_build(benchmark, corpus):
    """Cold construction of every typed parser the corpus uses."""
    names = sorted({name for name, _ in corpus.files})

    def build():
        get_typed_parser.cache_clear()
        for name in names:
            get_typed_parser(name)

    benchmark.group = "typed-grammar-build"
    benchmark.extra_info["n_components"] = len(names)
    benchmark.pedantic(build, rounds=ROUNDS, iterations=1)
