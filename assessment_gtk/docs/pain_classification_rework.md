# Tab 05 (Pain Type Classification) rework — field-id decision table

Status: **Phase 1 — planning artifact, not yet built.** Source paper: Shraim et al.,
*Pain* 167(7):1669–1682 (2026), "Towards a tool to discriminate between pain mechanistic
descriptors" (`workfiles/Towards a tool to discriminate between pain...  Pain.pdf`).
Decided with the user 2026-10-10 (see chat log for full reasoning behind each call).

Scope: `assessment_gtk/gpab_assessment/sections/pain_classification.py`, the three
report emitters in `assessment/pab_assessment/storage.py` (clean MD, dev MD, raw/docx),
`update_cross_refs()`, `search.py`, `grid_overview.py`, and a new local KB content file.
Work happens on `dev` only.

## Ground rules locked in with the user

- **Schema break accepted, no migration.** `save_all_sections()` replaces the whole
  `pain_classification` sub-dict per save (`data["assessment"][key] = val`, confirmed
  in `storage.py`) — the first gpab save of this tab on any existing session wipes
  `infl_*`/`cs_*`/retired keys for that session. Accepted, by design, no migration step.
- Fields with no equivalent in the paper's ranked lists are **not deleted outright** —
  they become a starred, nested "legacy/supplementary" subgroup per pain type, each
  with a KB note explaining why it's there. This is the same treatment approved for
  the Inflammatory 4-flag subgroup (nested under Nociceptive item 4).
- Negation-worded paper items ("No generalised hypersensitivity", "Absence of autonomic
  symptoms") are kept **verbatim**, not restated positively — accepted as mildly awkward
  but deliberate.
- Items genuinely ambiguous in the paper itself ("more concern for bodily function") are
  dropped; the rest of the lowest-weighted items (imaging findings, both descriptors) are
  kept.
- BACPAP stays exactly as-is and becomes the **canonical store** for every nociplastic
  item that overlaps it (items 4, 8, 9, 10, 15 below) — same `field_id`, same widget
  state, rendered a second time inside Nociplastic rather than duplicated as separate
  fields. Granularity in Nociplastic matches BACPAP's own (e.g. 5 separate hypersensitivity
  flags for item 8, not one combined flag).
- RFIQ/FCSS (items 11/12) are being added as new entries, *not* assumed equivalent to the
  existing Fibromyalgia WPI/SS (Wolfe 2016) subscale — needs an explicit compare-and-report
  step before wiring (see "Open items" below).
- DN4/NPQ/PainDETECT cutoffs are built here, with a flagged TODO that they're also
  candidates for the Outcome Measures tab later (not built there now).

## Nociceptive — reordered by relative weight (Table 6)

| Rank | Weight | Paper item | Field id | Disposition |
|---|---|---|---|---|
| 1 | 15.5% | Pain consistently provoked/aggravated by specific movements/postures, proportionally | `noci_subj_mechanical` | reuse, relabel |
| 2 | 15.1% | Clear, consistent, proportional pattern on mechanical/movement testing | `noci_exam_mechanical` | reuse, relabel |
| 3 | 14.4% | Localised distribution of pain | `noci_subj_localised` | reuse |
| 4 | 13.0% | Signs of inflammation (redness/heat/warmth/tenderness/swelling) | `noci_subj_inflammation` (anchor) + nested starred subgroup `infl_constant/morning/sleep/activity` (+ existing 0–4 score, ≥2 alert) | reuse as anchor; nest the 4-flag subgroup beneath it, KB note citing the paper's own "might require expansion... stiffness and time-dependent pain variation" line + Walker & Williamson 2008 |
| 5 | 11.8% | No generalised hypersensitivity | `noci_subj_no_gen_hypersensitivity` | new, verbatim |
| 6 | 10.5% | Scores on modified PainDETECT ≤12 | `noci_painDETECT_score` | new, numeric cutoff entry |
| 7 | 10.4% | Absence of autonomic symptoms/signs | `noci_subj_no_autonomic` | new, verbatim |
| 8 | 9.4% | Imaging findings of potential relevance | `noci_imaging` | new |
| — | — | *(legacy/supplementary, starred, no paper match)* | `noci_subj_trauma`, `noci_subj_resolving`, `noci_subj_no_constant`, `noci_exam_palpation`, `noci_exam_hyperalgesia`, `noci_exam_antalgic` | kept, nested starred group |
| — | — | *(removed)* | `noci_subj_analgesia`, `noci_subj_recent` | dropped |
| — | — | Likelihood, Interpretation | `noci_likelihood`, `noci_interpretation` | kept, unranked |
| — | — | *(retired — Inflammatory no longer an independent pain type)* | `infl_likelihood` | dropped (folds into `noci_likelihood`) |

## Neuropathic — reordered by relative weight (Table 7)

| Rank | Weight | Paper item | Field id | Disposition |
|---|---|---|---|---|
| 1 | 10.9% | Diagnostic test confirming lesion/disease of somatosensory system | `neuro_diagnostic_test` | new |
| 2 | 10.4% | Sensory signs on exam in same plausible distribution | `neuro_exam_neurology` | reuse, relabel (sensory-only now — see item 9) |
| 3 | 9.8% | Pain quality descriptors — electric/shooting/stinging/flashing | `neuro_subj_quality` | reuse |
| 4 | 9.5% | Pain in neuroanatomically plausible distribution | `neuro_subj_dermatomal` | reuse |
| 5 | 8.8% | Nonpainful sensory symptoms — numbness/pins-and-needles/crawling | `neuro_subj_neurological` | reuse, relabel |
| 6 | 8.1% | Heat-related sensory symptoms | `neuro_heat_sensory` | new, split out of old combined `neuro_subj_dysaesthesia` |
| 7 | 7.8% | Cold-related sensory symptoms | `neuro_cold_sensory` | new, split out |
| 8 | 7.0% | DN4 score ≥4 | `neuro_dn4_score` | new, numeric cutoff |
| 9 | 7.0% | Motor symptoms/signs (reduced/absent DTRs, weakness, atrophy) | `neuro_exam_motor` | new — separated from item 2, which the paper keeps sensory-only |
| 10 | 6.0% | Neuropathic Pain Questionnaire above cutoff | `neuro_npq_score` | new, numeric cutoff |
| 11 | 5.9% | Pain aggravated by movements loading/compressing neural tissue | `neuro_subj_neural_loading` | reuse |
| 12 | 5.3% | Phantom pain | `neuro_phantom` | new |
| 13 | 3.6% | Muscle spasticity in plausible distribution | `neuro_spasticity` | new, lowest-weighted, kept |
| — | — | *(legacy/supplementary, starred)* | `neuro_subj_nerve_injury`, `neuro_subj_severity`, `neuro_subj_spontaneous`, `neuro_exam_neurodynamic`, `neuro_exam_neural_palpation`, `neuro_exam_antalgic`, `neuro_exam_hyperalgesia` | kept, nested starred group |
| — | — | *(removed)* | `neuro_subj_medication` | dropped |
| — | — | *(retired — split into items 6/7)* | `neuro_subj_dysaesthesia` | dropped |
| — | — | Likelihood, Interpretation | `neuro_likelihood`, `neuro_interpretation` | kept |

## Nociplastic — reordered by relative weight (Table 8), Central Sensitisation dissolved in

| Rank | Weight | Paper item | Field id | Disposition |
|---|---|---|---|---|
| 1 | 7.7% | Diffuse/widespread/regional/poorly-localised/varying distribution | `nocip_subj_widespread` | reuse, relabel; **absorbs** `nocip_subj_disproportionate` (folded in per user call) |
| 2 | 7.1% | Generalised hypersensitivity | `nocip_generalised_hypersensitivity` | new |
| 3 | 6.8% | Multisite pain (3+ regions) or spread over time | `nocip_multisite` | new |
| 4 | 6.1% | Multiple somatic symptoms (fatigue, sleep w/ nocturnal awakening, mood, cognitive) | **shared with BACPAP**: `bacpap_como_sleep`, `bacpap_como_fatigue`, `bacpap_como_cognitive` | reused verbatim, same field ids/widget state; absorbs `cs_fatigue`/`cs_sleep`/`cs_concentration` |
| 5 | 6.1% | Mechanical testing disproportionate/inconsistent/nonmechanical pattern | `nocip_exam_disproportionate` | reuse |
| 6 | 6.1% | Pain in nonneuroanatomically plausible distribution | `nocip_nonneuroanatomical` | new; **absorbs** `nocip_exam_diffuse` (folded in, per user call 2026-10-10 — not an exact match, accepted) |
| 7 | 5.4% | CSI score ≥40 | `csi_score` | moved in verbatim from dissolved Central Sensitisation block, existing ≥40 alert logic kept |
| 8 | 5.3% | Hypersensitivity in region — touch/pressure/movement/heat/cold | **shared with BACPAP**: `bacpap_hyper_touch/movement/pressure/heat/cold` (5 flags) | reused verbatim; absorbs `cs_touch`/`cs_temperature` |
| 9 | 5.3% | Hypersensitivity — sound/light/odour/taste | **shared with BACPAP**: `bacpap_como_sensory` | reused verbatim; absorbs `cs_light`/`cs_noise` (and partially `cs_pesticides` — see Open items) |
| 10 | 5.3% | Evoked hypersensitivity to touch/pressure, clinically elicited | **shared with BACPAP**: `bacpap_static`, `bacpap_dynamic` | reused verbatim |
| 11 | 5.0% | RFIQ score (no cutoff proposed) | `nocip_rfiq_score` | new, non-alerted score entry — **cross-check vs Fibromyalgia WPI/SS before wiring, see Open items** |
| 12 | 5.0% | FCSS score (no cutoff proposed) | `nocip_fcss_score` | new, non-alerted score entry — same cross-check |
| 13 | 4.8% | Inconsistent/confusing/ambiguous test responses | `nocip_inconsistent_responses` | new |
| 14 | 4.6% | Absent/inconsistent (not plausible) sensory/motor signs | `nocip_absent_inconsistent_signs` | new |
| 15 | 4.4% | Evoked hypersensitivity to heat/cold, clinically elicited | **shared with BACPAP**: `bacpap_thermal` | reused verbatim |
| 16 | 4.2% | Variability/inconsistency in pain-quality descriptors | `nocip_variable_descriptors` | new |
| 17 | 4.1% | No imaging findings | `nocip_no_imaging` | new |
| 18 | 4.0% | Pain present for more than 3 months | `nocip_subj_persistent` | reuse (was "beyond healing timeframes" — close enough in meaning to relabel rather than add a new field) |
| 19 | 2.8% | *(more concern for bodily function)* | — | **omitted** — paper itself flags this item as ambiguously interpreted by respondents |
| — | — | *(legacy/supplementary, starred)* | `nocip_subj_disproportionate2`, `nocip_subj_spontaneous`, `nocip_subj_disability`, `nocip_subj_constant`, `nocip_subj_night_pain`, `nocip_subj_dysaesthesia`, `nocip_subj_severity` | kept, nested starred group |
| — | — | *(legacy/supplementary — no clean paper or BACPAP match)* | `cs_swelling`, `cs_tingling` | kept, nested starred group (not dropped despite Central Sensitisation subsection dissolving) |
| — | — | *(legacy/supplementary — generic catch-all, kept alongside the now-granular BACPAP-shared flags)* | `nocip_exam_hyperalgesia` | kept, starred — confirmed 2026-10-10 |
| — | — | *(removed)* | `nocip_subj_failed`, `nocip_subj_psychosocial`, `nocip_subj_medication`, `nocip_exam_psychosocial` | dropped |
| — | — | *(imperfect fit, accepted)* | `cs_pesticides` | folded into item 9 (`bacpap_como_sensory`) — not an exact match (chemical/pesticide ≠ odour), accepted per user call 2026-10-10 |
| — | — | Likelihood, Interpretation | `nocip_likelihood`, `nocip_interpretation` | kept |

## Unchanged

Fibromyalgia (`fm_*`), BACPAP (`bacpap_*` as the pre-existing block, now also referenced
from Nociplastic as above), Summary (`summary_dominant`/`summary_contributing`/`summary_reasoning`).

## Cross-reference (`xref_*`) re-pointing

| Key | Currently reads | After rework |
|---|---|---|
| `xref_infl_morning` | `infl_morning` | unchanged — field still exists, nested under Nociceptive item 4 |
| `xref_infl_sleep` | `infl_sleep` | unchanged, same reason |
| `xref_infl_dx` | (not field-tied) | unchanged |
| `xref_noci_resolving` | `noci_subj_resolving` | unchanged — field kept in Nociceptive legacy group |
| `xref_neuro_neurological` | `neuro_subj_neurological` | unchanged — field kept (item 5) |
| `xref_nocip_failed` | `nocip_subj_failed` | **retired** — field removed |
| `xref_nocip_psych` | `nocip_subj_psychosocial` | **retired** — field removed |
| `xref_nocip_night` | `nocip_subj_night_pain` | unchanged — field kept in legacy group |
| `xref_nocip_dx` | (not field-tied) | unchanged |
| `xref_cs_fatigue` | `cs_fatigue` | **re-point** to `bacpap_como_fatigue` |
| `xref_cs_sleep` | `cs_sleep` | **re-point** to `bacpap_como_sleep` |
| `xref_cs_concentration` | `cs_concentration` | **re-point** to `bacpap_como_cognitive` |
| `xref_cs_tingling` | `cs_tingling` | unchanged — field kept in legacy group |

## Open items — resolved 2026-10-10

Three fields turned up during the final accounting pass that weren't covered by earlier
rounds of questions. User confirmed all three dispositions above, explicitly accepting
that not every mapping is an exact clinical match — some entries don't carry over
precisely, or are merged with other fields, and that's OK:

1. `nocip_exam_diffuse` → folded into item 6 (`nocip_nonneuroanatomical`).
2. `nocip_exam_hyperalgesia` → kept as a generic catch-all, starred, alongside the
   granular BACPAP-shared hypersensitivity flags.
3. `cs_pesticides` → folded into item 9 (`bacpap_como_sensory`), not an exact match
   (chemical/pesticide sensitivity ≠ odour sensitivity) but accepted.

**Phase 1 is complete.** This table is now the frozen source of truth for Phases 2–6.

## Next steps

- Phase 2: KB data file (weight/rank/criterion/reference table + extended `KBEntry`)
- Phase 3: GTK section rebuild
- Phase 4: KB panel wiring
- Phase 5: report emitters (clean MD, dev MD, raw/docx) + docx
- Phase 6: `search.py` / `grid_overview.py` reindex
