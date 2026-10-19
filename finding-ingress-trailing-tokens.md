# Keyword/scalar rows keep trailing tokens

**FIXED** on branch `roundtrip-fixes` (`25611a5`).

**Layer:** ingress Pass 1 (`converter/ingress/structure.py:733-741`).
**Fixed by the simplification:** yes, by the Phase 2 value parsers
(keyword → presence, scalar → `row[1]`).

Pass 1 stores `list(row[1:])` whenever a row has more than two tokens,
whatever the field's type. Real files have trailing inline comments and
extra values that MF6 ignores:

    PRINT_INPUT (echo input to listing file)   -> print_input = ['(echo', 'input', ...]
    SAVE_FLOWS bcf2ss.cbb (file for ...)       -> save_flows  = ['bcf2ss.cbb', '(file', ...]
    under_relaxation none dbd                  -> under_relaxation = ['none', 'dbd']
    outer_maximum 100 500                      -> outer_maximum = [100, 500]

Egress then drops keyword/string ones (reload gives `False`/`None`), and
IMS integer/double ones fail to write:

    TypeError: 'int' object is not iterable   (codec/writer/filters.py:238)

Value diffs (17): test004_bcfss, test005_advgw_tidal, test006_gwf3_tr,
test006_gwf3_tr_nr, test011_mflgr_ex3, test023_FlowingWell,
test027_TimeseriesTest, test027_TimeseriesTest_idomain, test028_sfr,
test028_sfr_mvr, test028_sfr_mvr_openclose, test029_lgrsfr_parent,
test032_sfr, test051_uzfp2, test051_uzfp2TS, test051_uzfp2_nouzf,
test051_uzfp2_openclose.
Write failures (3, IMS): test013_Zaidel, test044_lakebotfill_dev,
test045_lake2tr_nr.

Fix direction: dispatch on field type (`to_field_type`). Keyword →
`True`. Integer/double/string/file → `row[1]`. Inline array (shape
metadata) → `row[1:]`. Record → `from_tokens`.

Correction: quoted strings are *not* single tokens in the basic grammar;
see finding 10.
