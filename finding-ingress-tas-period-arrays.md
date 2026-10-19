# TAS-sourced G/A period arrays are dropped on load

**Layer:** ingress Pass 3b (`converter/ingress/structure.py:343`).
**Fixed by the simplification:** not without a **representation
decision**.

A period array can reference a time-array series instead of holding
literal data:

    BEGIN PERIOD 1
      RECHARGE  TIMEARRAYSERIES  RchSeries
    END PERIOD

Ingress consumes the row and discards it. That period's slice stays all
`FILL_DNODATA`, which egress reads as "fill forward, omit the block", so
the reference is lost on write. If every period is TAS-sourced, the
reloaded field comes back 0-d / default instead of `(nper, ncpl)`.

Confirmed: test027_TimeseriesTest `rcha.recharge` loads as all 3e30 (and
the same for `_idomain`). The `TAS6 FILEIN` option itself is kept.

The dense `(nper, ...)` representation (decision 1 in the plan) has no way
to say "period k comes from TAS `<name>`". Options include a per-period
reference map on the field or package, or a sentinel plus a side table.
The TAS values can't be substituted in, because MF6 interpolates them in
time within a period.
