# Aux-named G/A period arrays are dropped on load

**Layer:** ingress Pass 3b (`_parse_readarray_period_block`,
`converter/ingress/structure.py:347`).
**Fixed by the simplification:** yes, in Phase 3 (aux names from the load
context become tagged keys of the `aux` field).

In READASARRAYS packages, `AUXILIARY <names>` lets each name appear as its
own array in period blocks:

    BEGIN PERIOD 1
      RECHARGE
        CONSTANT 0.01
      MYRCHMULT
        CONSTANT 2.
    END PERIOD

Ingress reads the control record, so parsing stays aligned, and then
throws the value away. `aux` stays all `FILL_DNODATA` (3e30). Egress
already writes per-aux-name arrays, so this only goes one way.

Confirmed: test027_TimeseriesTest `rcha.aux` loads as all 3e30. Also
present in test001h_rch_array1/3/4, test001h_evt_array1/3/4,
test004_bcfss, but finding 1 hides those from the round-trip survey.

Not visible in loaded-vs-reloaded (lost on both sides). Needs a targeted
test: load, then assert `aux` equals the source values.
