# Tokenizer splits ISO datetimes

**FIXED** on branch `roundtrip-fixes` (`6937743`).

**Layer:** reader grammar (`flopy4/mf6/codec/reader/grammar/basic.lark`).
**Fixed by the simplification:** no.

`START_DATE_TIME 1997-07-16T19:20:30.45+01:00` tokenizes as
`[1997, '-07-16T19:20:30.45+01:00']`: `NUMBER` wins over the `word` regex
for the leading `1997`, even though `word`'s character class matches the
whole token. Pass 1 then stores the list, and the TDIS writer fails:

    TypeError: 'int' object is not iterable   (codec/writer/filters.py:238)

Impact: TDIS fails to write in 21 models, so those models can't be
round-trip checked at all. They include `test001h_rch_array1..4` and
`test001h_evt_array1..4`, which are the aux-named period array cases
(finding 6).

Affected: test001a_Tharmonic, test001a_Tharmonic_tabs, test001h_drn_list4,
test001h_{evt,rch}_{array,list}{1..4}, test001i_gwf-gwf, test001i_multilayer.

Wider than dates: any token with a leading digit split the same way (a
file name `1model.ts` gave `[1, 'model.ts']`). Fixed by making `NUMBER`
match only a whole token.

Still open: Fortran `D` exponents (`1D-5`, `8.2d-4`) now lex as a single
word (a str) instead of a split `[1, 'D-5']`, but not as a number. MF6
reads them as numbers. They appear in the corpus only in fields nothing
loads yet (NPF `DEV_OMEGA`, which no loaded `Npf` field takes, and LAK
outlets, which has no class), so no loaded value is affected today. The
fix would be `[eEdD]` in the `NUMBER` exponent and `d`→`e` before
`float()`.

Original fix direction: make the lexer prefer the longer match for tokens like this
(for example a word terminal priority, or a `NUMBER` that can't be followed
by word characters). Check that the typed grammar (`typed.lark`) doesn't
have the same issue.
