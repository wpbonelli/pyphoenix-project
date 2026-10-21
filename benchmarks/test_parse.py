"""Parse benchmarks: flopy4's basic vs. typed parsers over the real MF6 corpus.

Measures only getting file *text* into Python, per file. For a full
simulation load (and flopy3), see `test_load.py`.

The corpus is every package file the benchmark models (``--bench-tier``
or ``--bench-manifest``) resolve, narrowed to files *both* grammars parse
as-is, so basic and typed time identical input. `n_files`/`n_bytes` are recorded in each benchmark's
`extra_info`: when comparing runs across a grammar change, check they
match, since a file the changed grammar newly rejects silently drops out.

To compare grammar variants on identical input, pin the corpus with
``--bench-parse-manifest PATH``: the first run (on the stricter variant)
writes the file list it used, and later runs use exactly that list,
failing loudly if any listed file no longer parses.

Benchmarks (each parametrized by parser, ``basic`` or ``typed``):

- `test_parse` -- Lark lex + parse only; where a grammar change shows up.
- `test_parse_transform` -- parse plus the Lark transformer, i.e.
  ``loads_basic`` / ``loads_typed``.
- `test_typed_grammar_build` -- cold construction of the typed parsers,
  excluded from the two above, with no on-disk cache.
- `test_typed_grammar_load` -- the same parsers from a warm on-disk cache
  (see `get_typed_parser`), a cold start after the first.
"""

import functools
import logging
import warnings
from pathlib import Path
from typing import NamedTuple

import pytest
from _models import known_passing, selection
from _ops import load_flopy4, package_files

ROUNDS = 3


class Corpus(NamedTuple):
    files: list[tuple[str, str]]  # (dfn_name, text)

    @property
    def info(self) -> dict:
        return {
            "n_files": len(self.files),
            "n_bytes": sum(len(text) for _, text in self.files),
            "n_components": len({name for name, _ in self.files}),
        }


@pytest.fixture(scope="module")
def corpus(request, tmp_path_factory) -> Corpus:
    from modflow_devtools.models import copy_to

    from flopy4.mf6.codec.reader import loads_basic, loads_typed
    from flopy4.mf6.codec.reader.parser import get_typed_parser

    manifest: Path | None = request.config.getoption("bench_parse_manifest")
    pinned = set(manifest.read_text().split()) if manifest and manifest.exists() else None
    files: list[tuple[str, str]] = []
    keys: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.disable(logging.CRITICAL)
        try:
            if pinned is not None:
                names = sorted(known_passing())
                names = [n for n in names if any(k.startswith(n + "/") for k in pinned)]
            else:
                names = selection(request.config).names
            for model_name in names:
                workspace = copy_to(tmp_path_factory.mktemp("bench"), model_name, verbose=False)
                if workspace is None or not (workspace / "mfsim.nam").exists():
                    continue
                sim = load_flopy4(workspace)
                for path, dfn_name in package_files(sim, workspace):
                    key = f"{model_name}/{path.relative_to(workspace).as_posix()}"
                    if pinned is not None and key not in pinned:
                        continue
                    text = path.read_text()
                    try:
                        _basic_parser().parse(text)
                        get_typed_parser(dfn_name).parse(text)
                        loads_basic(text)
                        loads_typed(text, dfn_name)
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
    return Corpus(files)


@functools.cache
def _basic_parser():
    """The basic grammar's parser, without the reader's transformer, which
    `BASIC_PARSER` applies as it parses (see `get_basic_parser`)."""
    from flopy4.mf6.codec.reader.parser import get_basic_parser

    return get_basic_parser()


def _parse_basic(corpus: Corpus) -> None:
    for _, text in corpus.files:
        _basic_parser().parse(text)


def _parse_typed(corpus: Corpus) -> None:
    from flopy4.mf6.codec.reader.parser import get_typed_parser

    for name, text in corpus.files:
        get_typed_parser(name).parse(text)


def _parse_transform_basic(corpus: Corpus) -> None:
    from flopy4.mf6.codec.reader import loads_basic

    for _, text in corpus.files:
        loads_basic(text)


def _parse_transform_typed(corpus: Corpus) -> None:
    from flopy4.mf6.codec.reader import loads_typed

    for name, text in corpus.files:
        loads_typed(text, name)


@pytest.mark.parametrize("parser", ["basic", "typed"])
def test_parse(benchmark, corpus, parser):
    fn = _parse_basic if parser == "basic" else _parse_typed
    benchmark.group = "parse"
    benchmark.extra_info.update(corpus.info)
    benchmark.pedantic(fn, args=(corpus,), rounds=ROUNDS, iterations=1)


@pytest.mark.parametrize("parser", ["basic", "typed"])
def test_parse_transform(benchmark, corpus, parser):
    fn = _parse_transform_basic if parser == "basic" else _parse_transform_typed
    benchmark.group = "parse-transform"
    benchmark.extra_info.update(corpus.info)
    benchmark.pedantic(fn, args=(corpus,), rounds=ROUNDS, iterations=1)


def _typed_grammars(benchmark, corpus, group: str) -> None:
    from flopy4.mf6.codec.reader.parser import get_typed_parser

    names = sorted({name for name, _ in corpus.files})

    def build():
        get_typed_parser.cache_clear()
        for name in names:
            get_typed_parser(name)

    build()  # fills the cache, if there is one
    benchmark.group = group
    benchmark.extra_info["n_components"] = len(names)
    benchmark.pedantic(build, rounds=ROUNDS, iterations=1)
    get_typed_parser.cache_clear()


def test_typed_grammar_build(benchmark, corpus, monkeypatch):
    """Cold construction of every typed parser the corpus uses."""
    monkeypatch.setenv("FLOPY4_CACHE_DIR", "")
    _typed_grammars(benchmark, corpus, "typed-grammar-build")


def test_typed_grammar_load(benchmark, corpus, monkeypatch, tmp_path):
    """Every typed parser the corpus uses, from a warm on-disk cache."""
    monkeypatch.setenv("FLOPY4_CACHE_DIR", str(tmp_path))
    _typed_grammars(benchmark, corpus, "typed-grammar-load")
