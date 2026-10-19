# Repeated TS6 FILEIN: last one wins

**Layer:** ingress Pass 1 (`converter/ingress/structure.py:714`).
**Fixed by the simplification:** yes, in Phase 3. It needs the
field-level `repeats` flag from devtools, and the field type becomes
`list[Path]` (a user API change).

MF6 accumulates every `TS6 FILEIN <f>` row (IDM `load_io_tag`). Ingress
assigns each one to the same kwarg, so only the last survives.

Confirmed: `Wel.load(test106_tsnodata/alt_model/model.wel)` (5 × `TS6`)
gives `ts_file = model_well5_pump.ts`. `alt_model` isn't referenced from
`mfsim.nam`, so a test has to load the WEL file directly.

The other corpus case, `test051_uzfp2TS/uzfp2.uzf` (2 × `TS6`), is on
UZF, which has no generated class, so it isn't loaded at all (finding 9).

Not visible in loaded-vs-reloaded. Needs a targeted test.
