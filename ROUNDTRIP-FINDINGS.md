# Round-trip findings (2026-09-23)

Found while setting up Phase 0 of `docs/dev/converter-simplification-plan.md`.
All pre-existing on `develop` (`fe5423c`).

## Method

`roundtrip_survey.py` loads, writes, and reloads each of the 239 non-`large`
`KNOWN_PASSING` corpus models, then diffs every block field of every
component with `roundtrip_compare.py`:

    pixi run -e dev python roundtrip_survey.py <outdir>   # ~20s on 12 workers

Result on `fe5423c`: **183 identical, 31 differ, 25 fail to write.**
After fixes #1-#5 (branch `roundtrip-fixes`, `25611a5`): **233 identical,
6 differ, 0 fail to write**. The 6 are 3 TAS models (#8) and 3 benign 0-d
vs. broadcast differences.

Loaded-vs-reloaded can't see a value that ingress drops, because it's
missing on both sides. Those were confirmed separately by loading the source
files, and they need targeted source-vs-loaded tests.

## Findings

| # | file | layer | models | fixed by the simplification? |
|---|---|---|---|---|
| 1 | [finding-tokenizer-iso-datetime.md](finding-tokenizer-iso-datetime.md) | reader grammar | 21 (write fails) | **fixed** `6937743` |
| 2 | [finding-writer-float-precision.md](finding-writer-float-precision.md) | writer | 5 | **fixed** `c986857` |
| 3 | [finding-writer-model-subdirs.md](finding-writer-model-subdirs.md) | writer | 1 (write fails) | **fixed** `a08c862` |
| 4 | [finding-ingress-trailing-tokens.md](finding-ingress-trailing-tokens.md) | ingress Pass 1 | 20 (3 write fails) | **fixed** `25611a5` |
| 5 | [finding-ingress-single-auxiliary.md](finding-ingress-single-auxiliary.md) | ingress Pass 1 | 23 (16 hidden by #1) | **fixed** `25611a5` |
| 6 | [finding-ingress-aux-period-arrays.md](finding-ingress-aux-period-arrays.md) | ingress Pass 3b | ≥ 7 | yes (Phase 3) |
| 7 | [finding-ingress-repeated-ts6.md](finding-ingress-repeated-ts6.md) | ingress Pass 1 | 2 | yes (Phase 3, needs devtools `repeats`) |
| 8 | [finding-ingress-tas-period-arrays.md](finding-ingress-tas-period-arrays.md) | ingress Pass 3b | 2+ | needs a representation decision first |
| 9 | [finding-ungenerated-packages-skipped.md](finding-ungenerated-packages-skipped.md) | coverage | many | no (codegen coverage) |
| 10 | [finding-tokenizer-quoted-strings.md](finding-tokenizer-quoted-strings.md) | reader grammar | 0 in corpus | no |

Not a bug: a constant array loaded 0-d (`sto.sy = 0.15`) reloads broadcast
to full shape (3 × `test020_NevilleTonkinTransient*`). Equal values;
comparisons should broadcast.

## Sequencing (proposed 2026-09-23)

See "Sequencing" under Phases in `docs/dev/converter-simplification-plan.md`.
In short, the Phase 0 harness and fixes #1, #3, #2, #4 and #5 land on develop
first; #6, #7 and #8 are left to the simplification; #9 is separate.

Decided (2026-09-23):
- #2: the default float writing becomes lossless.
- #4 and #5: fix on develop.

## Status and next steps (roundtrip-fixes worktree)

- Worktree `~/dev/pyphoenix-roundtrip-fixes`, branch `roundtrip-fixes`,
  off `origin/develop` at `fe5423c`. No upstream set and nothing pushed.
- Done (2026-09-23), one signed commit each, smoke passing:
  - `c1e4678` harness: `test/mf6/test_mf6_roundtrip.py`, a corpus round
    trip with strict xfails listed by cause, plus targeted xfail tests for
    #6, #7 and #8
  - `6937743` #1 tokenizer (NUMBER only as a whole token)
  - `a08c862` #3 writer mkdir for model subdirectories
  - `c986857` #2 lossless floats by default
  - `25611a5` #4 and #5 Pass 1 takes option values by field type
- Remaining xfails: 3 TAS models in the round trip (#8), and the targeted
  tests for #6, #7 and #8. Those are left to the simplification.
- New, not fixed: #10 quoted strings; `D` exponents (a note under #1);
  exchanges and `Simulation` options unmodeled (added to #9).
- Next: decide whether to open a PR from `roundtrip-fixes`, then rebase
  `pyphoenix-simplify-converter` onto it and start Phase 1.
