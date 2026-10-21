import hashlib
import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import lark
from lark import Lark, Transformer
from lark.lexer import BasicLexer, ContextualLexer, LexerState, LexerThread, LineCounter

_LALR = "lalr"
_GRAMMAR_MODULE = Path(__file__).parent / "grammar"


class _Text:
    """A buffer as lark's lexer reads its input (a `TextSlice`'s
    attributes), which only matches regexes on it."""

    __slots__ = ("text", "start", "end")

    def __init__(self, buffer) -> None:
        self.text = buffer
        self.start = 0
        self.end = len(buffer)


class _BufferLexerThread(LexerThread):
    """Lexes any buffer (a file's mmap), not just `str` or `bytes`. Lark
    passes other input here as is."""

    @classmethod
    def from_custom_input(cls, lexer, text) -> LexerThread:
        return cls(lexer, LexerState(_Text(text), LineCounter(b"\n")))  # type: ignore[arg-type]


class _Numbers(bytes):
    """A NUMBERS match whose `str` is empty, so the token doesn't copy its
    text; the transformer reads it by position (see
    `BasicTransformer.NUMBERS`)."""

    __slots__ = ()

    def __str__(self) -> str:
        return ""


class _BytesLexer(BasicLexer):
    def match(self, text, pos):
        res = super().match(text, pos)
        if res is not None and res[1] == "NUMBERS":
            return _Numbers(res[0]), res[1]
        return res


class _BytesContextualLexer(ContextualLexer):
    BasicLexer = _BytesLexer


def get_basic_parser(transformer: Transformer | None = None, use_bytes: bool = False) -> Lark:
    """The basic grammar's parser. With a transformer, `parse` applies it
    as it goes, never holding the whole tree, whose tokens copy the text
    they matched twice over (a big block's many times the file's size).
    With `use_bytes`, it parses bytes or a buffer (a file's mmap), so the
    text needn't be in memory."""
    grammar_path = _GRAMMAR_MODULE / "basic.lark"
    with open(grammar_path, "r") as f:
        return Lark(
            f.read(),
            parser=_LALR,
            debug=True,
            import_paths=[str(_GRAMMAR_MODULE)],
            transformer=transformer,
            use_bytes=use_bytes,
            _plugins=(
                {"LexerThread": _BufferLexerThread, "ContextualLexer": _BytesContextualLexer}
                if use_bytes
                else {}
            ),
        )


def _cache_root() -> Path | None:
    """Where built typed parsers are cached: `FLOPY4_CACHE_DIR` if it's set
    (empty for no cache), else the platform's user cache directory."""
    if (env := os.environ.get("FLOPY4_CACHE_DIR")) is not None:
        return Path(env) if env else None
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "flopy4"


def _build_typed(grammar: str) -> Lark:
    return Lark(
        grammar,
        parser=_LALR,
        debug=True,
        import_paths=[str(_GRAMMAR_MODULE)],
    )


@lru_cache(maxsize=None)
def get_typed_parser(name: str) -> Lark:
    """`name`'s typed parser, built when it's first asked for. A built
    parser is cached on disk (see `_cache_root`), keyed by its grammar, the
    shared grammar it imports, and lark's and Python's versions, so it's
    built once for each. Not lark's own `cache` option, which writes the
    file in place, so a concurrent process (pytest-xdist) could read it
    half-written, or two could interleave their writes."""
    grammar_path = _GRAMMAR_MODULE / "generated" / f"{name}.lark"
    if not grammar_path.exists():
        raise FileNotFoundError(f"Grammar file not found: {grammar_path}")
    grammar = grammar_path.read_text()
    if (root := _cache_root()) is None:
        return _build_typed(grammar)
    key = hashlib.sha256(
        "\0".join(
            [
                grammar,
                (_GRAMMAR_MODULE / "typed.lark").read_text(),
                lark.__version__,
                "%d.%d" % sys.version_info[:2],
            ]
        ).encode()
    ).hexdigest()[:16]
    path = root / "grammars" / f"{name}-{key}.pickle"
    try:
        with open(path, "rb") as f:
            return Lark.load(f)
    except Exception:
        # Missing, or corrupt: build it, as lark's own cache does.
        pass
    parser = _build_typed(grammar)
    _save(parser, path)
    return parser


def _save(parser: Lark, path: Path) -> None:
    """Write `parser` to `path` atomically, removing its grammar's stale
    entries. A cache that can't be written (a read-only home) is skipped."""
    temp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as f:
            temp = Path(f.name)
            parser.save(f)
        os.replace(temp, path)
        name = path.name.rsplit("-", 1)[0]
        for stale in path.parent.glob(f"{name}-*.pickle"):
            if stale != path and stale.name.rsplit("-", 1)[0] == name:
                stale.unlink(missing_ok=True)
    except OSError:
        if temp is not None:
            temp.unlink(missing_ok=True)
