# Writer rounds float arrays

**FIXED** on branch `roundtrip-fixes` (`c986857`).

**Layer:** writer (`WriteContext.float_precision`, default 8, i.e. `%.8e`:
`flopy4/mf6/write_context.py:57,142`; `codec/writer/filters.py`).
**Fixed by the simplification:** no.

Constants were written `%.8e` (9 significant digits) and internal arrays
`%.9e` (10), so source values with more precision change on round trip.
For example, test061_csub_jacob's `delc CONSTANT 100.58491653` was written
as `1.00584917e+02`.

Affected (value diffs in `delr`, `delc`, `strt`): test033_wtdecay,
test061_csub_holly, test061_csub_jacob, test120_mv_dis-lgr,
test120_mv_dis-lgr_3models.

**DECIDED (2026-09-23): the default becomes lossless.** Use the shortest
string that reads back to the same double (`repr`, or numpy
`format_float_positional`/`format_float_scientific` with `unique=True`),
not `%.17g`, so `0.01` stays `0.01`. `WriteContext(float_precision=n)`
stays as an opt-in for rounding. This changes the formatting of every
written file, so any saved expected output (for example `test/__compare__`)
has to be updated in the same change.
