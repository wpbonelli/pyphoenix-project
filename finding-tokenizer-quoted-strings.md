# Quoted strings with spaces are split into tokens

**Layer:** reader grammar (`flopy4/mf6/codec/reader/grammar/basic.lark`).
**Fixed by the simplification:** no.

The basic grammar's `word` terminal has no quoted-string form, so a quoted
value with spaces splits on whitespace, and a double quote isn't a word
character at all:

    crs 'a b c'                          -> ['crs', "'a", 'b', "c'"]
    crs 'PROJCS["NAD83 / UTM zone 11N"]' -> parse error at '"'

The writer does emit this form: `quote_if_needed` single-quotes WKT
strings, and `test_ncf_wkt_write` writes one. So a WKT `CRS` (DIS/DISV/
DISU) or NCF `WKT` can be written but not read back. Since `25611a5`, a
split string option takes only its first token (`"'a"`). Before that it
became a list of the pieces; both are wrong.

No corpus model uses a quoted value with spaces, so the round-trip test
doesn't cover it.

Fix direction: add a quoted-string terminal to `basic.lark`
(`/'[^'\n]*'|"[^"\n]*"/`) that `item` accepts, and strip the quotes in
the transformer (Pass 1 already has `_strip_quotes` for paths).
