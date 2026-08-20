# Field Key Reference

Complete list of every field ID used across the assessment and objective TUI.
The `id` is the JSON storage key and the widget ID in Python — **never rename it**.

Use this file to find the correct key when writing a KB entry. For KB entries,
the key in `objective/kb/<region>.yaml` must match the row `id` in the form
driver YAML (for YAML-driven fields) or the widget id= in the Python section
file (for hardcoded fields). Bilateral keys use the stem (without `_l`/`_r`).

Jump to a section:
- [Subjective — 01 Consent](#01-consent)
- [Subjective — 02 Subjective History / Behaviour / Management / Activity / Work](#02-subjective)
- [Subjective — 02 Sleep (YAML pilot)](#02-sleep-yaml-pilot)
- [Subjective — 02 24-Hour Pattern / Psychosocial / Goals / Suicide Risk](#02-24hr-psychosocial-suicide)
- [Subjective — 03 Medical Screening](#03-medical-screening)
- [Subjective — 04 Pain Classification](#04-pain-classification)
- [Subjective — 05 Outcome Measures](#05-outcome-measures)
- [Subjective — 06 Diagnosis](#06-diagnosis)
- [Subjective — 07 Barriers](#07-barriers)
- [Subjective — 08 Rx & Plan](#08-rx--plan)
- [Objective — 01 General Observations](#obj-01-general-observations)
- [Objective — 04 Neurological](#obj-04-neurological)
- [Objective — 05 Sensory](#obj-05-sensory)
- [Objective — 07 Functional](#obj-07-functional)
- [Objective — Lumbar YAML fields (02/06/08)](#objective-lumbar-yaml-fields)
- [Objective — Cervical YAML fields (02/03/06/08)](#objective-cervical-yaml-fields)
- [Objective — Shoulder YAML fields (02/03/06/08)](#objective-shoulder-yaml-fields)

---

## 01 Consent

| Key | Description |
|---|---|
| `preferred_name_input` | Patient's preferred name |
| `patient_expectations` | Patient's stated expectations for treatment |
| `reason_for_attending` | Reason for attending |
| `cause_understanding_detail` | Patient's understanding of their condition cause |
| `prognosis_expectations` | Patient's expectations about prognosis |
| `treatment_preference` | Stated treatment preference |

---

## 02 Subjective

### History

| Key | Description |
|---|---|
| `onset` | Onset description |
| `duration` | Duration of current episode |
| `context_at_onset` | Context / activity at onset |
| `previous_episodes` | Previous episodes of this condition |
| `previous_treatment` | Previous treatment received |

### Behaviour

| Key | Description |
|---|---|
| `behaviour_boom_bust` | Boom-bust behaviour flag |
| `behaviour_boom_bust_text` | Boom-bust notes |
| `behaviour_avoidance` | Avoidance behaviour flag |
| `behaviour_avoidance_text` | Avoidance notes |
| `behaviour_endurance` | Endurance behaviour flag |
| `behaviour_endurance_text` | Endurance notes |
| `behaviour_flareups` | Flare-ups flag |
| `behaviour_flareups_text` | Flare-ups notes |

### Self-Management

| Key | Description |
|---|---|
| `pain_control_score` | Pain control score (NRS) |
| `flareup_prevention` | Strategies used to prevent flare-ups |
| `management_strategies` | Current self-management strategies |
| `confidence_score` | Self-efficacy / confidence score |

### Activity & Exercise

| Key | Description |
|---|---|
| `pre_activity_level` | Pre-injury activity level |
| `current_activity_level` | Current activity level |
| `exercise_type` | Type of exercise currently doing |
| `exercise_dose` | Exercise dose (frequency, duration) |
| `exercise_response` | Symptomatic response to exercise |

### Work

| Key | Description |
|---|---|
| `pre_injury_role` | Pre-injury job role |
| `pre_injury_hours` | Pre-injury hours worked |
| `pre_injury_duties` | Pre-injury duties / physical demands |
| `current_work_status` | Current work status |
| `current_hours` | Current hours worked |
| `current_duties` | Current duties / modified duties |

---

## 02 Sleep (YAML pilot)

These fields are defined in `pab_assessment/sections/yaml/subj_sleep_pilot.yaml`.

| Key | Description |
|---|---|
| `sleep_overall_rating` | Overall sleep quality rating (Good / Tolerable / Poor) |
| `sleep_feels_rested` | Feels rested on waking (Yes / Sometimes / No) |
| `sleep_time_to_bed` | Time to bed (TIB start — clock hh:mm) |
| `sleep_time_attempt` | Time attempting to sleep (clock hh:mm) |
| `sleep_onset_time` | Time of actual sleep onset — Sleep Onset Latency (SOL, clock hh:mm) |
| `sleep_waso_clock` | Clock time of most significant night waking (clock hh:mm) |
| `sleep_waso_duration` | Total wake duration after sleep onset (WASO, elapsed hh:mm) |
| `sleep_awake_in_bed` | Time awake in bed after final wakeup (WIBA, elapsed hh:mm) |
| `sleep_awake_out_bed` | Time awake out of bed during night (WOOB, elapsed hh:mm) |
| `sleep_final_wakeup` | Final wake-up time (FWT, clock hh:mm) |
| `sleep_time_out_of_bed` | Time out of bed — end of TIB (TOB, clock hh:mm) |
| `sleep_efficiency` | Calculated sleep efficiency — read-only, auto-computed (%) |
| `sleep_postural_factors` | Postural / positional factors affecting sleep (text) |
| `sleep_environment_quality` | Sleep environment quality (text) |
| `sleep_daytime_naps` | Daytime nap duration (elapsed hh:mm) |
| `sleep_overall_comments` | Overall sleep comments (text) |

---

## 02 24-Hour Pattern / Psychosocial / Suicide Risk

### 24-Hour Pattern

| Key | Description |
|---|---|
| `hr24_am` | Morning symptom pattern |
| `hr24_day` | Daytime symptom pattern |
| `hr24_pm` | Evening symptom pattern |
| `hr24_nocte` | Night (nocte) symptom pattern |
| `energy_levels` | Energy levels through day |
| `daily_pattern_comments` | Daily pattern summary comments |

### Psychosocial

| Key | Description |
|---|---|
| `mood_text` | Mood (free text) |
| `social_situation` | Social situation |
| `financial_status` | Financial status |
| `cultural_considerations` | Cultural considerations |
| `psychological_distress` | Psychological distress description |
| `screening_tool` | Screening tool used (DASS, PHQ, etc.) |

### SMART Goals

| Key | Description |
|---|---|
| `goal_1` – `goal_4` | Patient goals 1–4 |

### Suicide / Self-Harm Risk

| Key | Description |
|---|---|
| `harm_plan` | Self-harm plan present |
| `harm_means` | Self-harm means available |
| `harm_intent` | Self-harm intent |
| `harm_action` | Action taken (safeguarding) |

---

## 03 Medical Screening

| Key | Description |
|---|---|
| `previous_injuries` | Previous injuries (text) |
| `comorbid_other` | Other comorbidities (text) |
| `rf_malignancy_comment` | Malignancy red flag — clinician comment |
| `rf_fracture_comment` | Fracture red flag — clinician comment |
| `rf_infection_comment` | Infection red flag — clinician comment |
| `cauda_equina_action` | Cauda equina — action taken |
| `spinal_cord_action` | Spinal cord compression — action taken |
| `diff_as_action` | Ankylosing spondylitis screening — action |
| `diff_aaa_action` | Abdominal aortic aneurysm screening — action |
| `diff_vc_action` | Vascular claudication screening — action |

Toggle buttons (CheckButton / FlagButton) in the Medical section are harvested
dynamically by the search index. They have IDs beginning with `rf_`, `cvd_`,
`comorbid_`, `diff_` prefixes — see `sections/medical.py` for the full list.

| Key | Description |
|---|---|
| `img_xray` | Imaging — X-ray (CheckButton) |
| `img_xray_detail` | Imaging — X-ray detail (text) |
| `img_us` | Imaging — Ultrasound (CheckButton) |
| `img_us_detail` | Imaging — Ultrasound detail (text) |
| `img_ct` | Imaging — CT (CheckButton) |
| `img_ct_detail` | Imaging — CT detail (text) |
| `img_mri` | Imaging — MRI (CheckButton) |
| `img_mri_detail` | Imaging — MRI detail (text) |
| `img_ncs` | Imaging — NCS (CheckButton) |
| `img_ncs_detail` | Imaging — NCS detail (text) |
| `img_other` | Imaging — Other (CheckButton) |
| `img_other_detail` | Imaging — Other detail (text) |

---

## 04 Pain Classification

| Key | Description |
|---|---|
| `noci_interpretation` | Nociceptive pain — clinician interpretation |
| `neuro_interpretation` | Neuropathic pain — clinician interpretation |
| `nocip_interpretation` | Nociplastic pain — clinician interpretation |
| `csi_score` | Central Sensitisation Inventory score |
| `fm_wpi` | FM: Widespread Pain Index score (0–19) |
| `fm_fatigue` | FM: Fatigue severity (0–3) |
| `fm_waking` | FM: Waking unrefreshed severity (0–3) |
| `fm_cognitive` | FM: Cognitive symptoms severity (0–3) |
| `fm_headaches` | FM: Headaches present |
| `fm_ibs` | FM: IBS present |
| `fm_depression` | FM: Depression present |
| `fm_duration` | FM: Symptoms ≥ 3 months |
| `fm_exclusion` | FM: No alternative explanation |
| `bacpap_chronic` | BACPAP: LBP ≥ 3 months |
| `bacpap_distribution` | BACPAP: Regional/widespread distribution |
| `bacpap_nociceptive` | BACPAP: Nociceptive pain mainly responsible |
| `bacpap_neuropathic` | BACPAP: Neuropathic pain mainly responsible |
| `bacpap_static` | BACPAP: Static mechanical allodynia |
| `bacpap_dynamic` | BACPAP: Dynamic mechanical allodynia |
| `bacpap_thermal` | BACPAP: Heat or cold allodynia |
| `bacpap_after` | BACPAP: Painful after-sensations |
| `bacpap_hyper_touch` | BACPAP: Hypersensitivity — touch |
| `bacpap_hyper_movement` | BACPAP: Hypersensitivity — movement |
| `bacpap_hyper_pressure` | BACPAP: Hypersensitivity — pressure |
| `bacpap_hyper_heat` | BACPAP: Hypersensitivity — heat |
| `bacpap_hyper_cold` | BACPAP: Hypersensitivity — cold |
| `bacpap_como_sensory` | BACPAP: Comorbid — light/sound/odour sensitivity |
| `bacpap_como_sleep` | BACPAP: Comorbid — sleep disturbance |
| `bacpap_como_fatigue` | BACPAP: Comorbid — fatigue |
| `bacpap_como_cognitive` | BACPAP: Comorbid — cognitive problems |
| `bacpap_notes` | BACPAP: Clinician notes |
| `summary_contributing` | Contributing factor summary |
| `summary_reasoning` | Pain classification reasoning |

---

## 05 Outcome Measures

| Key | Description |
|---|---|
| `psfs_act_1` – `psfs_act_3` | PSFS activity names 1–3 |
| `psfs_act_1_score` – `psfs_act_3_score` | PSFS activity scores 1–3 (/10) |
| `bpi_activity` | BPI: Activity interference |
| `bpi_mood` | BPI: Mood interference |
| `bpi_walking` | BPI: Walking interference |
| `bpi_work` | BPI: Work interference |
| `bpi_relations` | BPI: Relations interference |
| `bpi_sleep` | BPI: Sleep interference |
| `bpi_enjoyment` | BPI: Enjoyment interference |
| `dass_dep_score` | DASS: Depression subscale score |
| `dass_anx_score` | DASS: Anxiety subscale score |
| `dass_str_score` | DASS: Stress subscale score |
| `phq4_nervous` | PHQ-4: Nervous/anxious item (0–3) |
| `phq4_worry` | PHQ-4: Uncontrollable worry item (0–3) |
| `phq4_noint` | PHQ-4: No interest item (0–3) |
| `phq4_depressed` | PHQ-4: Depressed/hopeless item (0–3) |
| `pcs_rum_score` | PCS: Rumination |
| `pcs_mag_score` | PCS: Magnification |
| `pcs_help_score` | PCS: Helplessness |
| `pcs_total_score` | PCS: Total score |
| `pseq_score` | PSEQ score (/60) |
| `pseq_interp` | PSEQ interpretation |
| `pseq2_score` | PSEQ-2 score (/12, 2-item screen) |
| `pseq2_interp` | PSEQ-2 interpretation (Severe ≤5 / Moderate 6–9 / Adequate ≥10) |
| `pcl5_score` | PCL-5 score |
| `pcl5_action` | PCL-5 — action taken |
| `isi_score` | ISI (Insomnia Severity Index) score |
| `pbas_score` | PBAS score |
| `add_audit` | AUDIT administered (bool) |
| `add_dudit` | DUDIT administered (bool) |
| `add_epoc` | EPOC / additional measures notes |
| `add_other` | Other additional measures notes |
| `plan_psfs` | Intent to use PSFS (bool) |
| `plan_bpi` | Intent to use BPI (bool) |
| `plan_dass` | Intent to use DASS-21 (bool) |
| `plan_phq4` | Intent to use PHQ-4 (bool) |
| `plan_pcs` | Intent to use PCS (bool) |
| `plan_pseq` | Intent to use PSEQ (bool) |
| `plan_pcl5` | Intent to use PCL-5 (bool) |
| `plan_sleep` | Intent to use sleep measures (bool) |
| `plan_additional` | Intent to use additional measures (bool) |
| `hyp_0_measure` – `hyp_2_measure` | Hypothesis test measure name |
| `hyp_0_baseline` – `hyp_2_baseline` | Hypothesis test baseline value |
| `hyp_0_interval` – `hyp_2_interval` | Hypothesis test interval |
| `hyp_0_rationale` – `hyp_2_rationale` | Hypothesis test rationale |

---

## 06 Diagnosis

CAL-CP (ICD-11 Chronic Pain Classification Algorithm, Korwisi et al 2021) walker
— see `sections/diagnosis.py` and `cal_cp_model.py`. One independent workup per
pain site; storage shape and live widget ids are both dynamic (a workup count
that varies at runtime), not a fixed field list, so this section documents the
*shape* rather than individual keys.

**Storage** (`diagnosis` in `_assessment.json`):

| Key | Description |
|---|---|
| `workups` | List of workup dicts, one per pain site (see below) |
| `legacy` | Pre-CAL-CP free-form fields, preserved verbatim if present (old `mechanism`/`primary_subtype`/etc — see "Legacy fields" below). Never written to by the current UI; only ever read back for display. |

**Workup dict** (`Workup.to_dict()` in `cal_cp_model.py`):

| Key | Description |
|---|---|
| `id` | Workup id, e.g. `"w1"`, `"w2"` — also the namespace suffix for that workup's widget ids (see below) |
| `label` | Site label, e.g. `"Left knee"` — shown as the tab title |
| `intro_done` | Whether the p6 chronic pain specifier form has been completed and the trunk walk started |
| `intro` | Dict of specifier answers: `onset_date`, `nrs_intensity`, `distress`, `interference`, `temporal_pattern` |
| `current_node_id` | Graph node id (e.g. `"n34"`) the walk is currently at |
| `path` | List of `{node_id, answer, merged}` steps taken so far |
| `finished` | Whether this workup has reached a diagnosis/terminal node |
| `result_summary` | Final ICD-11 code + name once finished, e.g. `"MG30.01 — Chronic widespread pain"` |

**Live widget ids** — every queryable widget is namespaced `<base>__<workup_id>`
since Textual keeps every workup's tab content mounted simultaneously (only the
active tab is visually hidden, not unmounted), so a plain id would collide the
instant a second workup existed:

| Base id | Description |
|---|---|
| `dx_add_workup` | "+ New workup" button (not namespaced — section-level) |
| `dx_node_box__<wid>` | Current trunk question / diagnosis display |
| `dx_restart__<wid>` | Restart this workup's walk |
| `dx_intro_start__<wid>` | "Start decision trunk" button |
| `dx_intro_label__<wid>` | Intro form: site label |
| `dx_intro_onset_date__<wid>` | Intro form: onset (MM/YYYY) |
| `dx_intro_nrs_intensity__<wid>` | Intro form: pain intensity NRS |
| `dx_intro_distress__<wid>` | Intro form: distress NRS |
| `dx_intro_interference__<wid>` | Intro form: interference NRS |
| `dx_intro_temporal__<wid>` | Intro form: temporal pattern (RadioSet) |

**Legacy fields** (pre-CAL-CP, `diagnosis.legacy.*` — read-only, never written by
current code; documented here only because old sessions may still carry them):

| Key | Description |
|---|---|
| `mechanism` | Pain mechanism selection |
| `primary_subtype` / `primary_severity` | Chronic primary pain subtype/severity |
| `surgical_procedure` / `surgical_source` / `surgical_subtype` / `surgical_severity` | Post-surgical pain fields |
| `traumatic_event` / `traumatic_source` / `traumatic_subtype` / `traumatic_severity` | Post-traumatic pain fields |
| `msk_pathology` / `msk_source` / `msk_subtype` / `msk_severity` | Secondary MSK pain fields |
| `neuro_lesion` / `neuro_subtype` / `neuro_severity` | Neuropathic pain fields |
| `mixed_dominant` / `mixed_reasoning` | Mixed/indeterminate pain fields |

---

## 07 Barriers

| Key | Description |
|---|---|
| `bi_movement_region` | Movement restriction — region |
| `bi_strength_other` | Other strength deficit — detail |
| `bi_deep_other` | Other deep stability deficit — detail |
| `bi_over_other` | Other overactivity — detail |
| `bi_nerve_region` | Nerve sensitisation — region |
| `bi_red_flag_detail` | Red flag barrier — detail |
| `bi_substance_detail` | Substance use barrier — detail |
| `custom_1_barrier` | Custom barrier 1 |
| `custom_1_strategy` | Custom strategy 1 |
| `custom_2_barrier` | Custom barrier 2 |
| `custom_2_strategy` | Custom strategy 2 |

---

## 08 Rx & Plan

| Key | Description |
|---|---|
| `tx_goal_orientation` | Goal orientation summary |
| `tx_formulation` | Treatment formulation |
| `tx_program` | Treatment programme |
| `tx_home_program` | Home programme |
| `tx_psychosocial` | Psychosocial treatment plan |
| `tx_medical` | Medical management plan |
| `tx_rtw` | Return to work plan |
| `s1_education` | Session 1: Education content |
| `s1_experiential` | Session 1: Experiential activity |
| `s1_confidence_nrs` | Session 1: Confidence NRS (0–10) |
| `s1_hw_other` | Session 1: Other homework |
| `fu_next_focus` | Follow-up: next session focus |
| `fu_monitoring` | Follow-up: monitoring plan |
| `fu_om_schedule` | Follow-up: outcome measure schedule |

### Miscellaneous

| Key | Description |
|---|---|
| `scratchpad_text` | Notes / Scratchpad (free text) |

---

## Obj 01 General Observations

These fields are in `objective/sections/general.py`.

### Physical measurements

| Key | Description |
|---|---|
| `go_height` | Height (cm) |
| `go_weight` | Weight (kg) |
| `go_bmi` | BMI (kg/m²) |
| `go_nrs` | Resting pain NRS (0–10) |
| `go_sit_tol` | Sitting tolerance during exam (min) |
| `go_transfer` | Transfer / undress distress (RadioGroup: None/Mild/Mod/Marked) |
| `go_transfer_cmt` | Transfer distress comment |

### Posture (RadioGroup: Normal / Mild / Moderate / Marked)

| Key | Description |
|---|---|
| `go_lx_lord` | Lumbar lordosis |
| `go_tx_kyph` | Thoracic kyphosis |
| `go_lean` | Antalgic lean (None / L / R / Variable) |
| `go_sway` | Sway-back posture (None / Mild / Mod / Marked) |
| `go_breath` | Breathing pattern (Normal / Apical / Paradox / Guarded) |
| `go_scap_l` | Left scapular position (Normal / Elevated / Winging / Protracted / Depressed) |
| `go_scap_r` | Right scapular position |
| `go_wasting` | Muscle wasting visible (None / Mild / Mod / Marked) |
| `go_posture_notes` | Posture free-text notes |


---

## Obj 04 Neurological

These fields are in `objective/sections/neurological.py`.
Bilateral fields exist as `{key}_l` and `{key}_r`.

### Upper limb reflexes (RadioGroup: 0 Absnt / 1+ Redu / 2+ Norm / 3+ Hypr / 4+Clons)

| Key stem | Description |
|---|---|
| `nr_biceps` | Biceps jerk (C5/6) — `nr_biceps_l`, `nr_biceps_r` |
| `nr_brad` | Brachioradialis jerk (C6) — `nr_brad_l`, `nr_brad_r` |
| `nr_triceps` | Triceps jerk (C7) — `nr_triceps_l`, `nr_triceps_r` |

### Upper limb myotomes (RadioGroup: 5/5 / 4/5 / 3/5 / 2/5 / 1/5 / 0/5)

| Key stem | Description |
|---|---|
| `nr_c5` | C5 — shoulder abduction (deltoid) — `nr_c5_l`, `nr_c5_r` |
| `nr_c6` | C6 — wrist extension (ECRL/ECRB) — `nr_c6_l`, `nr_c6_r` |
| `nr_c7` | C7 — elbow extension (triceps) — `nr_c7_l`, `nr_c7_r` |
| `nr_c8` | C8 — finger flexion (FDP) — `nr_c8_l`, `nr_c8_r` |
| `nr_t1` | T1 — finger abduction (interossei) — `nr_t1_l`, `nr_t1_r` |

### Upper limb dermatomes (RadioGroup: Absent / ↓Hypo / Normal / ↑Hyper)

| Key stem | Description |
|---|---|
| `sn_c5` | C5 — lateral arm / deltoid patch — `sn_c5_l`, `sn_c5_r` |
| `sn_c6` | C6 — thumb & index finger — `sn_c6_l`, `sn_c6_r` |
| `sn_c7` | C7 — middle finger — `sn_c7_l`, `sn_c7_r` |
| `sn_c8` | C8 — little finger / ulnar border — `sn_c8_l`, `sn_c8_r` |
| `sn_t1` | T1 — medial forearm — `sn_t1_l`, `sn_t1_r` |

### Upper limb neurodynamics (Input: free text response)

| Key | Description |
|---|---|
| `nr_ulnt1` | ULNT1 response (free text) |
| `nr_ulnt1_resp` | ULNT1 free-text response field |
| `nr_ulnt2a` | ULNT2a response |
| `nr_ulnt2a_resp` | ULNT2a free-text response |
| `nr_ulnt3` | ULNT3 response |
| `nr_ulnt3_resp` | ULNT3 free-text response |

### Lower limb reflexes (RadioGroup: 0 Absnt / 1+ Redu / 2+ Norm / 3+ Hypr / 4+Clons)

| Key stem | Description |
|---|---|
| `nr_knee` | Knee jerk (L3/4) — `nr_knee_l`, `nr_knee_r` |
| `nr_ankle` | Ankle jerk (S1) — `nr_ankle_l`, `nr_ankle_r` |

### Lower limb myotomes (RadioGroup: 5/5 / 4/5 / 3/5 / 2/5 / 1/5 / 0/5)

| Key stem | Description |
|---|---|
| `nr_l2` | L2 — hip flexion — `nr_l2_l`, `nr_l2_r` |
| `nr_l3` | L3 — knee extension — `nr_l3_l`, `nr_l3_r` |
| `nr_l4` | L4 — ankle dorsiflexion — `nr_l4_l`, `nr_l4_r` |
| `nr_l5` | L5 — great toe extension / EHL — `nr_l5_l`, `nr_l5_r` |
| `nr_s1` | S1 — plantarflexion / eversion — `nr_s1_l`, `nr_s1_r` |
| `nr_s2` | S2 — hamstrings / knee flexion — `nr_s2_l`, `nr_s2_r` |

### Lower limb dermatomes (RadioGroup: Absent / ↓Hypo / Normal / ↑Hyper)

| Key stem | Description |
|---|---|
| `sn_l2` | L2 — anterior thigh — `sn_l2_l`, `sn_l2_r` |
| `sn_l3` | L3 — medial knee — `sn_l3_l`, `sn_l3_r` |
| `sn_l4` | L4 — medial ankle — `sn_l4_l`, `sn_l4_r` |
| `sn_l5` | L5 — lateral leg / great toe — `sn_l5_l`, `sn_l5_r` |
| `sn_s1` | S1 — lateral foot / heel — `sn_s1_l`, `sn_s1_r` |
| `sn_s2` | S2 — posterior thigh — `sn_s2_l`, `sn_s2_r` |

### Lower limb neurodynamics (Input: free text response)

| Key | Description |
|---|---|
| `nr_slr` | SLR RadioGroup response (has degree input) |
| `nr_slr_deg` | SLR degree of onset |
| `nr_slr_resp` | SLR free-text response |
| `nr_slump` | Slump free-text response |
| `nr_slump_resp` | Slump free-text response field |
| `nr_pkf` | PKF (prone knee flexion) response (has degree input) |
| `nr_pkf_deg` | PKF degree of onset |
| `nr_pkf_resp` | PKF free-text response |

### UMN signs (CheckButton)

| Key | Description |
|---|---|
| `nr_umn_hyper` | Hyperreflexia present |
| `nr_umn_bab` | Babinski positive |
| `nr_umn_clonus` | Clonus present |
| `nr_umn_romberg` | Romberg positive |
| `nr_umn_coord` | Coordination impaired |
| `nr_umn_hoffman` | Hoffman's sign positive (FlagButton) |
| `nr_umn_tromner` | Tromner sign positive (FlagButton) |
| `nr_umn_lhermitte` | Lhermitte's sign positive (FlagButton) |
| `nr_umn_inv_sup` | Inverted Supinator sign positive (FlagButton) |
| `nr_ul_reflex_notes` | UL Reflexes subsection free-text notes |
| `nr_ul_myotome_notes` | UL Myotomes subsection free-text notes |
| `nr_ul_derm_notes` | UL Dermatomes subsection free-text notes |
| `nr_ul_nd_notes` | UL Neurodynamics subsection free-text notes |
| `nr_ll_reflex_notes` | LL Reflexes subsection free-text notes |
| `nr_ll_myotome_notes` | LL Myotomes subsection free-text notes |
| `nr_ll_derm_notes` | LL Dermatomes subsection free-text notes |
| `nr_ll_nd_notes` | LL Neurodynamics subsection free-text notes |
| `nr_umn_notes` | UMN Signs subsection free-text notes |
| `nr_notes` | Neurological general free-text notes |

---

## Obj 05 Sensory

These fields are in `objective/sections/sensory.py`.
Boolean fields (CheckButton); detail fields (Input, suffix `_detail`).

### Hyposensitivity

| Key | Description |
|---|---|
| `sn_sharp_blunt` | Sharp/blunt discrimination impaired (Neuropen) |
| `sn_sharp_blunt_detail` | Sharp/blunt — detail |
| `sn_tpd` | Two-point discrimination reduced |
| `sn_tpd_detail` | TPD — detail |
| `sn_lt` | Light touch hypoaesthesia present |
| `sn_lt_detail` | Light touch — detail |
| `sn_body` | Body perception impaired |
| `sn_body_detail` | Body perception — free-text detail (TextArea) |

### Hypersensitivity / Central sensitisation signs

| Key | Description |
|---|---|
| `sn_static_allodynia` | Static mechanical allodynia (monofilament) |
| `sn_static_allodynia_detail` | Static allodynia — detail |
| `sn_dynamic_allodynia` | Dynamic mechanical allodynia (brush) |
| `sn_dynamic_allodynia_detail` | Dynamic allodynia — detail |
| `sn_secondary_hyper` | Secondary hyperalgesia (algometer / PPT) |
| `sn_secondary_hyper_detail` | PPT — detail |
| `sn_ppt` | PPT severity (RadioGroup: None/Mild/Mod/Marked) |
| `sn_ppt_detail` | PPT reading / threshold detail |
| `sn_pin_prick` | Pin prick hyperalgesia |
| `sn_pin_prick_detail` | Pin prick — detail |
| `sn_cold` | Cold hyperalgesia (ice 5 s) |
| `sn_cold_detail` | Cold hyperalgesia — detail |
| `sn_heat` | Heat hyperalgesia |
| `sn_heat_detail` | Heat hyperalgesia — detail |
| `sn_temporal_sum` | Temporal summation present |
| `sn_temporal_sum_detail` | Temporal summation — detail |
| `sn_cpm` | Conditioned pain modulation — dysfunctional response present |
| `sn_cpm_detail` | CPM — detail (baseline PPT / cold pressor pain / post-PPT) |
| `sn_nerve_palpation` | Upper limb nerve trunk palpation — sensitivity present |
| `sn_nerve_palpation_detail` | Nerve trunk palpation — detail (site(s)) |
| `sn_notes` | Sensory free-text notes |

---

## Obj 07 Functional

These fields are in `objective/sections/functional.py`.

### Functional movement quality (RadioGroup)

| Key | Description |
|---|---|
| `ft_gait` | Gait quality (Normal / Antalgic / Ataxic) |
| `ft_phr` | Prone hip rotation (Bilateral / Unilateral) |
| `ft_sts_q` | Sit-to-stand quality (Normal / Limited / Unable) |
| `ft_sls_l` | Single-leg stance left quality |
| `ft_sls_r` | Single-leg stance right quality |

### Balance — timed seconds (GridInput)

| Key | Description |
|---|---|
| `ft_bal_both` | Balance — both legs normal stance (s) |
| `ft_bal_feet` | Balance — feet together (s) |
| `ft_bal_tandem` | Balance — tandem stance (s) |
| `ft_sls_eo_l` | SLS eyes open — left (s) |
| `ft_sls_eo_r` | SLS eyes open — right (s) |
| `ft_sls_ec_l` | SLS eyes closed — left (s) |
| `ft_sls_ec_r` | SLS eyes closed — right (s) |
| `ft_sls_foam_l` | SLS foam 10cm — left (s) |
| `ft_sls_foam_r` | SLS foam 10cm — right (s) |

### Timed capability (GridInput)

| Key | Description |
|---|---|
| `ft_tug` | Timed Up and Go 3m (s) |
| `ft_sts5` | 5× Sit-to-Stand (s) |
| `ft_10m_e` | 10m walk comfortable pace (m/s) |
| `ft_10m_f` | 10m walk fast pace (m/s) |
| `ft_2mw` | 2-minute walk test (m) |
| `ft_notes` | Functional free-text notes |

---

## Objective Lumbar YAML fields

Defined in `objective/sections/yaml/lumbar.yaml`.
YAML-driven sections use the row `id` directly as widget ID (no prefix for
active movement / muscle testing RadioGroups; `st_` prefix for special tests).

### 02 Active Movement — Lumbar ROM

| Key | Widget ID | Description |
|---|---|---|
| `lx_flex` | `lx_flex_l`, `lx_flex_r` | Lumbar flexion (bilateral) |
| `lx_ext` | `lx_ext_l`, `lx_ext_r` | Lumbar extension (bilateral) |
| `lx_lf` | `lx_lf` | Lumbar lateral flexion |
| `lx_rot` | `lx_rot` | Lumbar rotation |
| `am_lx_notes` | `am_lx_notes` | Lumbar ROM notes (TextArea) |

### 02 Active Movement — Thoracic ROM

| Key | Widget ID | Description |
|---|---|---|
| `tx_flex` | `tx_flex_l`, `tx_flex_r` | Thoracic flexion (bilateral) |
| `tx_ext` | `tx_ext_l`, `tx_ext_r` | Thoracic extension (bilateral) |
| `tx_rot` | `tx_rot` | Thoracic rotation |
| `am_tx_notes` | `am_tx_notes` | Thoracic ROM notes (TextArea) |

### 06 Muscle Testing — Muscle Length (bilateral RadioGroup)

| Key | Widget ID | Description |
|---|---|---|
| `ml_ql` | `ml_ql_l`, `ml_ql_r` | QL (side sitting) |
| `ml_thomas` | `ml_thomas_l`, `ml_thomas_r` | Thomas test (hip flexors) |
| `ml_ham` | `ml_ham_l`, `ml_ham_r` | Hamstrings (SLR position) |

### 06 Muscle Testing — Muscle Activation (unilateral RadioGroup)

| Key | Widget ID | Description |
|---|---|---|
| `ma_tx_es` | `ma_tx_es` | Thoracic erector spinae |
| `ma_tva` | `ma_tva` | Transversus abdominis |
| `ma_lmf` | `ma_lmf` | Lumbar multifidus |
| `mu_notes` | `mu_notes` | Muscle testing notes (TextArea) |

### 06 Muscle Testing — Trunk Strength (numeric GridInput)

| Key | Widget ID | Description |
|---|---|---|
| `st_flex` | `st_flex` | Trunk flexion endurance (reps/min) |
| `st_ext` | `st_ext` | Trunk extension endurance (raises/min) |

### 08 Special Tests (CycleButton L/R pairs, storage key = `st_{stem}_l` / `st_{stem}_r`)

| Storage key (L) | Storage key (R) | KB stem | Group | Description |
|---|---|---|---|---|
| `st_slr_l` | `st_slr_r` | `slr` | Neurodynamics | Straight leg raise |
| `st_slump_l` | `st_slump_r` | `slump` | Neurodynamics | Slump test |
| `st_femoral_l` | `st_femoral_r` | `femoral` | Neurodynamics | Femoral nerve stretch |
| `st_crossed_slr_l` | `st_crossed_slr_r` | `crossed_slr` | Disc/Herniation | Crossed SLR |
| `st_faber_l` | `st_faber_r` | `faber` | Hip Screen | FABER (Patrick's) |
| `st_fadir_l` | `st_fadir_r` | `fadir` | Hip Screen | FADIR |
| `st_prone_inst_l` | `st_prone_inst_r` | `prone_inst` | Instability | Prone instability test |
| `st_lx_notes` | — | — | — | Special tests notes (TextArea) |

---

## Objective Cervical YAML fields

Defined in `objective/sections/yaml/cervical.yaml` (active movement, muscle, special tests)
and `objective/sections/cervical_tables.py` (passive, neck strength).

### 02 Active Movement — Cervical ROM

| Key | Widget ID | Description |
|---|---|---|
| `cx_flex` | `cx_flex_l`, `cx_flex_r` | Cervical flexion (bilateral:true — L only populated) |
| `cx_ext` | `cx_ext_l`, `cx_ext_r` | Cervical extension (bilateral:true — L only) |
| `cx_lf` | `cx_lf_l`, `cx_lf_r` | Cervical lateral flexion |
| `cx_rot` | `cx_rot_ax_l_range`, `cx_rot_ax_r_range` | Cervical rotation — DB-linked (Wainner CPR, "Cervical Rotation ROM (Involved Side)"), surfaces in the Regional Differential panel as a value row |
| `am_cx_notes` | `am_cx_notes` | Cervical ROM notes |

### 02 Active Movement — Thoracic ROM (cervical region)

| Key | Widget ID | Description |
|---|---|---|
| `tx_cx_flex` | `tx_cx_flex_l`, `tx_cx_flex_r` | Thoracic flexion (bilateral:true — L only) |
| `tx_cx_ext` | `tx_cx_ext_l`, `tx_cx_ext_r` | Thoracic extension (bilateral:true — L only) |
| `tx_cx_rot` | `tx_cx_rot_l`, `tx_cx_rot_r` | Thoracic rotation |
| `am_tx_cx_notes` | `am_tx_cx_notes` | Thoracic ROM notes (cervical region) |

### 03 Passive Movement — Overpressure (CervicalPassiveTables)

Widget IDs follow `{prefix}_ef` and `{prefix}_resp` pattern.

| Prefix | Description |
|---|---|
| `cx_op_flex` | Cervical flexion OP |
| `cx_op_ext` | Cervical extension OP |
| `cx_op_lf_l` | Lateral flexion left OP |
| `cx_op_lf_r` | Lateral flexion right OP |
| `cx_op_rot_l` | Rotation left OP |
| `cx_op_rot_r` | Rotation right OP |
| `cx_op_quad_l` | Quadrant left OP |
| `cx_op_quad_r` | Quadrant right OP |
| `cx_pm_op_notes` | Cervical OP notes (TextArea) |

### 03 Passive Movement — PAIVMs (CervicalPassiveTables)

Field IDs: `cx_pm_{level_key}_{direction}` — direction is `ul_l`, `c`, or `ul_r`.

| Level key | Display | Field IDs |
|---|---|---|
| `C0_1` | C0/1 | `cx_pm_C0_1_ul_l`, `cx_pm_C0_1_c`, `cx_pm_C0_1_ul_r` |
| `C1_2` | C1/2 | `cx_pm_C1_2_ul_l` … |
| `C2`–`C7` | C2–C7 | `cx_pm_C2_ul_l` … |
| `T1`–`T4` | T1–T4 | `cx_pm_T1_ul_l` … |
| `cx_pm_paivm_notes` | — | PAIVM notes (TextArea) |

### 06 Muscle Testing — Muscle Length (bilateral RadioGroup)

| Key | Widget ID | Description |
|---|---|---|
| `ml_ut` | `ml_ut_l`, `ml_ut_r` | Upper trapezius length |
| `ml_ls` | `ml_ls_l`, `ml_ls_r` | Levator scapulae length |
| `ml_pec` | `ml_pec_l`, `ml_pec_r` | Pectorals length |
| `ml_scal` | `ml_scal_l`, `ml_scal_r` | Scalenes length |

### 06 Muscle Testing — Muscle Activation (unilateral RadioGroup)

| Key | Widget ID | Description |
|---|---|---|
| `ma_dcf` | `ma_dcf` | Deep cervical flexors (CCFT) |
| `ma_cx_ext` | `ma_cx_ext` | Cervical extensors (prone head lift) |
| `ma_sa` | `ma_sa` | Serratus anterior |

### 06 Muscle Testing — Cervical Endurance and Neck Strength (CervicalMuscleTables)

| Key | Widget ID | Description |
|---|---|---|
| `st_dcf_end` | `st_dcf_end` | DCF endurance (chin tuck hold, seconds) |
| `cx_neck_flex` | `cx_neck_flex_l`, `cx_neck_flex_r` | Neck flexion strength (kg) |
| `cx_neck_ext` | `cx_neck_ext_l`, `cx_neck_ext_r` | Neck extension strength (kg) |
| `cx_neck_lf` | `cx_neck_lf_l`, `cx_neck_lf_r` | Neck lateral flexion strength (kg) |
| `cx_neck_rot` | `cx_neck_rot_l`, `cx_neck_rot_r` | Neck rotation strength (kg) |
| `mu_cx_notes` | `mu_cx_notes` | Muscle testing notes (TextArea) |

### 08 Special Tests (CycleButton widget ID = `st_{stem}_l` / `st_{stem}_r`)

Special tests use `BilateralGridSpecialTestsWidget`. CycleButton outer widget ID is the
storage key. KB entry key is the stem (the loader strips `_l`/`_r`).

| Widget ID (L) | Widget ID (R) | KB entry | Description |
|---|---|---|---|
| `st_spurling_l` | `st_spurling_r` | `spurling` | Spurling's (foraminal compression) |
| `st_distraction_l` | `st_distraction_r` | `distraction` | Cervical distraction |
| `st_ulnt1_l` | `st_ulnt1_r` | `ulnt1` | ULNT1 (median nerve bias) |
| `st_ulnt2a_l` | `st_ulnt2a_r` | `ulnt2a` | ULNT2a (radial nerve bias) |
| `st_ulnt3_l` | `st_ulnt3_r` | `ulnt3` | ULNT3 (ulnar nerve bias) |
| `st_frt_l` | `st_frt_r` | `frt` | FRT (cervicogenic headache) |
| `st_sharp_purser_l` | `st_sharp_purser_r` | `sharp_purser` | Sharp-Purser (UC instability) |
| `st_ant_shear_l` | `st_ant_shear_r` | `ant_shear` | Anterior shear (transverse lig) |
| `st_alar_sf_l` | `st_alar_sf_r` | `alar_sf` | Alar ligament side flexion |
| `st_alar_rot_l` | `st_alar_rot_r` | `alar_rot` | Alar ligament rotation stress |
| `st_lat_trans_l` | `st_lat_trans_r` | `lat_trans` | Lateral translation (UC) — no DB test row, YAML-only |
| `st_vbi_sus_rot_l` | `st_vbi_sus_rot_r` | `vbi_sus_rot` | VBI sustained rotation |
| `st_ccft_l` | `st_ccft_r` | DB-backed | CCFT (motor control) — L used clinically, R unused |
| `st_ccft_notes` | — | — | CCFT reminder notes (TextArea, heading "Lean angle · Nod · Lift · Hover") |
| `st_cx_notes` | — | — | Special tests notes (TextArea) |

Hoffman's sign moved to Neurological → UMN Signs (`nr_umn_hoffman`) along with Tromner,
Babinski, Lhermitte's, and Inverted Supinator — all five are Cook Myelopathy Cluster
signs and are grouped there instead of duplicating a bilateral row here.

---

## Objective Shoulder YAML fields

Defined in `objective/sections/yaml/shoulder.yaml` (active movement, muscle, special tests)
and `objective/sections/shoulder_tables.py` (passive OP/accessory/AC-SC, strength).

### 02 Active Movement — Shoulder ROM

All rows `bilateral: false` — separate L/R values.

| Key | Widget ID | Description |
|---|---|---|
| `sh_flex` | `sh_flex_l`, `sh_flex_r` | Shoulder flexion |
| `sh_ext` | `sh_ext_l`, `sh_ext_r` | Shoulder extension |
| `sh_abd` | `sh_abd_l`, `sh_abd_r` | Shoulder abduction |
| `sh_ir` | `sh_ir_l`, `sh_ir_r` | Internal rotation |
| `sh_er` | `sh_er_l`, `sh_er_r` | External rotation |
| `sh_hadd` | `sh_hadd_l`, `sh_hadd_r` | Horizontal adduction |
| `sh_hbb` | `sh_hbb_l`, `sh_hbb_r` | Hand behind back |
| `am_sh_notes` | `am_sh_notes` | Shoulder ROM notes |

### 02 Active Movement — Thoracic ROM (shoulder region)

| Key | Widget ID | Description |
|---|---|---|
| `tx_sh_flex` | `tx_sh_flex_l` | Thoracic flexion (bilateral:true — L only) |
| `tx_sh_ext` | `tx_sh_ext_l` | Thoracic extension (bilateral:true — L only) |
| `tx_sh_rot` | `tx_sh_rot_l`, `tx_sh_rot_r` | Thoracic rotation |
| `am_tx_sh_notes` | `am_tx_sh_notes` | Thoracic ROM notes (shoulder region) |

### 03 Passive Movement — Overpressure (ShoulderPassiveTables)

Field IDs follow `{prefix}_ef` and `{prefix}_resp`.

| Prefix | Description |
|---|---|
| `sh_op_flex` | Flexion OP |
| `sh_op_ext` | Extension OP |
| `sh_op_abd` | Abduction OP |
| `sh_op_ir` | Internal rotation OP |
| `sh_op_er` | External rotation OP |
| `sh_op_hadd` | Horizontal adduction OP |
| `sh_op_habd` | Horizontal abduction OP |
| `sh_pm_op_notes` | Shoulder OP notes (TextArea) |

### 03 Passive Movement — GH Accessory Glides (ShoulderPassiveTables)

Field IDs: `sh_acc_{direction}_{side}_{type}` — direction: `inf`, `post`, `ant`; side: `l`, `r`; type: `grade`, `resp`.

| Widget ID pattern | Description |
|---|---|
| `sh_acc_inf_l_grade` / `sh_acc_inf_l_resp` | Inferior glide left (Maitland grade + response) |
| `sh_acc_post_l_grade` / `sh_acc_post_l_resp` | Posterior glide left |
| `sh_acc_ant_l_grade` / `sh_acc_ant_l_resp` | Anterior glide left |
| `sh_acc_{dir}_r_grade` / `sh_acc_{dir}_r_resp` | Right-side equivalents |
| `sh_pm_acc_notes` | Accessory notes (TextArea) |

### 03 Passive Movement — AC / SC Joint (ShoulderPassiveTables)

| Widget ID (L) | Widget ID (R) | Description |
|---|---|---|
| `sh_ac_pm_stress_l` | `sh_ac_pm_stress_r` | AC joint stress |
| `sh_ac_pm_palp_l` | `sh_ac_pm_palp_r` | AC joint palpation |
| `sh_sc_pm_stress_l` | `sh_sc_pm_stress_r` | SC joint stress |

### 06 Muscle Testing — Muscle Length (bilateral RadioGroup)

| Key | Widget ID | Description |
|---|---|---|
| `ml_pec_min` | `ml_pec_min_l`, `ml_pec_min_r` | Pec minor length |
| `ml_pec_st` | `ml_pec_st_l`, `ml_pec_st_r` | Pec major sternal length |
| `ml_pec_cl` | `ml_pec_cl_l`, `ml_pec_cl_r` | Pec major clavicular length |
| `ml_lat` | `ml_lat_l`, `ml_lat_r` | Latissimus dorsi length |
| `ml_post_cap` | `ml_post_cap_l`, `ml_post_cap_r` | Posterior capsule length |

### 06 Muscle Testing — Muscle Activation (bilateral RadioGroup)

| Key | Widget ID | Description |
|---|---|---|
| `ma_lt` | `ma_lt_l`, `ma_lt_r` | Lower trapezius activation |
| `ma_sa` | `ma_sa_l`, `ma_sa_r` | Serratus anterior activation (bilateral) |
| `ma_er_fc` | `ma_er_fc_l`, `ma_er_fc_r` | ER force couple |
| `mu_sh_notes` | `mu_sh_notes` | Shoulder muscle notes (TextArea) |

### 06 Muscle Testing — Shoulder Strength (ShoulderMuscleTables, GridInput kg or 0–5)

| Key | Widget ID | Description |
|---|---|---|
| `sh_str_flex` | `sh_str_flex_l`, `sh_str_flex_r` | Shoulder flexion strength |
| `sh_str_abd` | `sh_str_abd_l`, `sh_str_abd_r` | Shoulder abduction strength |
| `sh_str_ir` | `sh_str_ir_l`, `sh_str_ir_r` | Internal rotation strength |
| `sh_str_er` | `sh_str_er_l`, `sh_str_er_r` | External rotation strength |
| `sh_str_scap` | `sh_str_scap_l`, `sh_str_scap_r` | Scaption strength |

### 08 Special Tests (CycleButton widget ID = `st_{stem}_l` / `st_{stem}_r`)

| Widget ID (L) | Widget ID (R) | KB entry | Description |
|---|---|---|---|
| `st_hawkins_l` | `st_hawkins_r` | `hawkins` | Hawkins-Kennedy (impingement) |
| `st_neer_l` | `st_neer_r` | `neer` | Neer sign (impingement) |
| `st_painful_arc_l` | `st_painful_arc_r` | `painful_arc` | Painful arc (impingement) |
| `st_empty_can_l` | `st_empty_can_r` | `empty_can` | Empty can / Jobe's (supraspinatus) |
| `st_full_can_l` | `st_full_can_r` | `full_can` | Full can (supraspinatus) |
| `st_er_lag_l` | `st_er_lag_r` | `er_lag` | ER lag sign (infraspinatus) |
| `st_lift_off_l` | `st_lift_off_r` | `lift_off` | Lift-off / Gerber's (subscapularis) |
| `st_belly_press_l` | `st_belly_press_r` | `belly_press` | Belly press / Napoleon (subscapularis) |
| `st_drop_arm_l` | `st_drop_arm_r` | `drop_arm` | Drop arm (full-thickness RC tear) |
| `st_cross_body_l` | `st_cross_body_r` | `cross_body` | Cross-body adduction (AC joint) |
| `st_ac_stress_l` | `st_ac_stress_r` | `ac_stress` | AC joint stress |
| `st_speeds_l` | `st_speeds_r` | `speeds` | Speed's test (biceps / SLAP) |
| `st_yergason_l` | `st_yergason_r` | `yergason` | Yergason's (bicipital groove) |
| `st_obrien_l` | `st_obrien_r` | `obrien` | O'Brien active compression (SLAP / AC) |
| `st_apprehension_l` | `st_apprehension_r` | `apprehension` | Apprehension (anterior instability) |
| `st_relocation_l` | `st_relocation_r` | `relocation` | Relocation / Jobe (anterior instability) |
| `st_sulcus_l` | `st_sulcus_r` | `sulcus` | Sulcus sign (inferior instability / MDI) |
| `st_scap_assist_l` | `st_scap_assist_r` | `scap_assist` | Scapular assistance (dyskinesis) |
| `st_wall_pushup_l` | `st_wall_pushup_r` | `wall_pushup` | Wall push-up (serratus anterior winging) |
| `st_er_resist_l` | `st_er_resist_r` | DB-backed | ER resistance (impingement, SIS cluster) |
| `st_irls_l` | `st_irls_r` | DB-backed | IR lag sign (subscapularis, RCT lag battery) |
| `st_drop_is_l` | `st_drop_is_r` | DB-backed | Drop sign (infraspinatus) — distinct from Drop Arm |
| `st_hornblower_l` | `st_hornblower_r` | DB-backed | Hornblower's (teres minor, RCT lag battery) |
| `st_ac_ext_l` | `st_ac_ext_r` | DB-backed | AC resisted extension (AC Joint Confirm Cluster) |
| `st_pass_comp_l` | `st_pass_comp_r` | DB-backed | Passive compression (SLAP tear) |
| `st_bicip_groove_l` | `st_bicip_groove_r` | DB-backed | Bicipital groove tenderness (Biceps TIC cluster) |
| `st_adson_l` | `st_adson_r` | DB-backed | Adson's (TOS) |
| `st_roos_l` | `st_roos_r` | DB-backed | Roos/EAST (TOS) |
| `st_wright_l` | `st_wright_r` | DB-backed | Wright's (TOS) |
| `st_crlf_l` | `st_crlf_r` | DB-backed | CRLF — helps rule cervical spine in/out of TOS |
| `st_sh_notes` | — | — | Special tests notes (TextArea) |

Shoulder is fully DB-backed as of this pass (`_DB_BACKED_REGIONS` in `kb_loader.py`) —
existing rows above still resolve via `kb/shoulder.yaml` as a fallback if the DB is
unreachable; the 10 new rows have no YAML fallback (no kb/shoulder.yaml entry authored
for them), so they show nothing rather than stale content if the DB is missing.

---

## Objective — Hip YAML fields (02/03/06/08)

### Hip — 02 Active Movement

| Left field | Right field | Notes |
|---|---|---|
| `hp_flex_ax_l_range` | `hp_flex_ax_r_range` | Flexion range (°) |
| `hp_ext_ax_l_range` | `hp_ext_ax_r_range` | Extension range |
| `hp_abd_ax_l_range` | `hp_abd_ax_r_range` | Abduction range |
| `hp_add_ax_l_range` | `hp_add_ax_r_range` | Adduction range |
| `hp_ir_ax_l_range` | `hp_ir_ax_r_range` | Int Rotation range |
| `hp_er_ax_l_range` | `hp_er_ax_r_range` | Ext Rotation range |
| `am_hp_notes` | — | Active movement notes (TextArea) |

### Hip — 03 Passive / OP (`hip_tables.py`)

| Left field | Right field | Notes |
|---|---|---|
| `hp_op_flex_l_norm` | `hp_op_flex_r_norm` | Flexion OP Normal toggle |
| `hp_op_flex_l_txt` | `hp_op_flex_r_txt` | Flexion OP text findings |
| `hp_op_ext_l_norm` | `hp_op_ext_r_norm` | Extension OP |
| `hp_op_abd_l_norm` | `hp_op_abd_r_norm` | Abduction OP |
| `hp_op_add_l_norm` | `hp_op_add_r_norm` | Adduction OP |
| `hp_op_ir_l_norm` | `hp_op_ir_r_norm` | Int Rotation OP |
| `hp_op_er_l_norm` | `hp_op_er_r_norm` | Ext Rotation OP |
| `hp_acc_dist_l_norm` | `hp_acc_dist_r_norm` | Distraction accessory |
| `hp_acc_lat_l_norm` | `hp_acc_lat_r_norm` | Lateral accessory |
| `hp_op_notes` | — | OP notes (TextArea) |

### Hip — 06 Muscle (`hip_tables.py`)

| Left field | Right field | Notes |
|---|---|---|
| `hp_str_flex_l` | `hp_str_flex_r` | Hip flexion strength |
| `hp_str_ext_l` | `hp_str_ext_r` | Hip extension strength |
| `hp_str_abd_l` | `hp_str_abd_r` | Hip abduction strength |
| `hp_str_add_l` | `hp_str_add_r` | Hip adduction strength |
| `hp_str_ir_l` | `hp_str_ir_r` | Hip int rotation strength |
| `hp_str_er_l` | `hp_str_er_r` | Hip ext rotation strength |
| `mu_hp_notes` | — | Muscle notes (TextArea) |

### Hip — 08 Special Tests (YAML-driven, KB key in parentheses)

| Left field | Right field | KB key | Test |
|---|---|---|---|
| `st_hp_fadir_l` | `st_hp_fadir_r` | `hp_fadir` | FADIR (FAI) |
| `st_hp_ant_imp_l` | `st_hp_ant_imp_r` | `hp_ant_imp` | Anterior Impingement |
| `st_hp_faber_l` | `st_hp_faber_r` | `hp_faber` | FABER (OA/SIJ) |
| `st_hp_hip_scour_l` | `st_hp_hip_scour_r` | `hp_hip_scour` | Hip Scour |
| `st_hp_log_roll_l` | `st_hp_log_roll_r` | `hp_log_roll` | Log Roll |
| `st_hp_ober_l` | `st_hp_ober_r` | `hp_ober` | Ober's (ITB/TFL) |
| `st_hp_trendelenburg_l` | `st_hp_trendelenburg_r` | `hp_trendelenburg` | Trendelenburg |
| `st_hp_sls_hip_l` | `st_hp_sls_hip_r` | `hp_sls_hip` | Single-Leg Stance |
| `st_hp_puranen_orava_l` | `st_hp_puranen_orava_r` | `hp_puranen_orava` | Puranen-Orava |
| `st_hp_bks_l` | `st_hp_bks_r` | `hp_bks` | Bent Knee Stretch |
| `st_hp_squeeze_l` | `st_hp_squeeze_r` | `hp_squeeze` | Squeeze (adductor) |
| `st_hp_notes` | — | — | Special tests notes (TextArea) |

---

## Objective — Knee YAML fields (02/03/06/08)

### Knee — 02 Active Movement

| Left field | Right field | Notes |
|---|---|---|
| `kn_flex_ax_l_range` | `kn_flex_ax_r_range` | Flexion range (°) |
| `kn_ext_ax_l_range` | `kn_ext_ax_r_range` | Extension range |
| `am_kn_notes` | — | Active movement notes (TextArea) |

### Knee — 03 Passive / OP (`knee_tables.py`)

| Left field | Right field | Notes |
|---|---|---|
| `kn_op_flex_l_norm` | `kn_op_flex_r_norm` | Flexion OP Normal toggle |
| `kn_op_flex_l_txt` | `kn_op_flex_r_txt` | Flexion OP text findings |
| `kn_op_ext_l_norm` | `kn_op_ext_r_norm` | Extension OP |
| `kn_acc_ap_l_norm` | `kn_acc_ap_r_norm` | AP Glide accessory |
| `kn_acc_pmed_l_norm` | `kn_acc_pmed_r_norm` | Patella medial glide |
| `kn_acc_plat_l_norm` | `kn_acc_plat_r_norm` | Patella lateral glide |
| `kn_op_notes` | — | OP notes (TextArea) |

### Knee — 06 Muscle (`knee_tables.py`)

| Left field | Right field | Notes |
|---|---|---|
| `kn_str_ext_l` | `kn_str_ext_r` | Knee extension / quads |
| `kn_str_flex_l` | `kn_str_flex_r` | Knee flexion / hamstrings |
| `kn_str_calf_l` | `kn_str_calf_r` | Calf / heel raise |
| `mu_kn_notes` | — | Muscle notes (TextArea) |

### Knee — 08 Special Tests (YAML-driven, KB key in parentheses)

| Left field | Right field | KB key | Test |
|---|---|---|---|
| `st_kn_lachman_l` | `st_kn_lachman_r` | `kn_lachman` | Lachman (ACL) |
| `st_kn_ant_draw_l` | `st_kn_ant_draw_r` | `kn_ant_draw` | Anterior Drawer (ACL) |
| `st_kn_pivot_l` | `st_kn_pivot_r` | `kn_pivot` | Pivot Shift (ACL) |
| `st_kn_post_draw_l` | `st_kn_post_draw_r` | `kn_post_draw` | Posterior Drawer (PCL) |
| `st_kn_post_sag_l` | `st_kn_post_sag_r` | `kn_post_sag` | Posterior Sag (PCL) |
| `st_kn_mcmurray_l` | `st_kn_mcmurray_r` | `kn_mcmurray` | McMurray's (meniscus) |
| `st_kn_thessaly_l` | `st_kn_thessaly_r` | `kn_thessaly` | Thessaly (meniscus) |
| `st_kn_jlt_l` | `st_kn_jlt_r` | `kn_jlt` | Joint Line Tenderness |
| `st_kn_valgus_0_l` | `st_kn_valgus_0_r` | `kn_valgus_0` | Valgus 0° (MCL/capsule) |
| `st_kn_valgus_30_l` | `st_kn_valgus_30_r` | `kn_valgus_30` | Valgus 30° (MCL) |
| `st_kn_varus_0_l` | `st_kn_varus_0_r` | `kn_varus_0` | Varus 0° (LCL/capsule) |
| `st_kn_varus_30_l` | `st_kn_varus_30_r` | `kn_varus_30` | Varus 30° (LCL) |
| `st_kn_clarkes_l` | `st_kn_clarkes_r` | `kn_clarkes` | Clarke's (PFJ) |
| `st_kn_pat_tilt_l` | `st_kn_pat_tilt_r` | `kn_pat_tilt` | Patella Tilt (PFJ) |
| `st_kn_pat_grind_l` | `st_kn_pat_grind_r` | `kn_pat_grind` | Patella Grind (PFJ) |
| `st_kn_notes` | — | — | Special tests notes (TextArea) |

---

## Objective — Ankle YAML fields (02/03/06/08)

### Ankle — 02 Active Movement

| Left field | Right field | Notes |
|---|---|---|
| `ak_df_ax_l_range` | `ak_df_ax_r_range` | Dorsiflexion range (°) |
| `ak_pf_ax_l_range` | `ak_pf_ax_r_range` | Plantarflexion range |
| `ak_inv_ax_l_range` | `ak_inv_ax_r_range` | Inversion range |
| `ak_ev_ax_l_range` | `ak_ev_ax_r_range` | Eversion range |
| `ak_wbdf_ax_l_range` | `ak_wbdf_ax_r_range` | WB Dorsiflexion (lunge) |
| `am_ak_notes` | — | Active movement notes (TextArea) |

### Ankle — 03 Passive / OP (`ankle_tables.py`)

| Left field | Right field | Notes |
|---|---|---|
| `ak_op_df_l_norm` | `ak_op_df_r_norm` | Dorsiflexion OP Normal toggle |
| `ak_op_df_l_txt` | `ak_op_df_r_txt` | Dorsiflexion OP text findings |
| `ak_op_pf_l_norm` | `ak_op_pf_r_norm` | Plantarflexion OP |
| `ak_op_inv_l_norm` | `ak_op_inv_r_norm` | Inversion OP |
| `ak_op_ev_l_norm` | `ak_op_ev_r_norm` | Eversion OP |
| `ak_acc_ap_l_norm` | `ak_acc_ap_r_norm` | AP Glide accessory |
| `ak_acc_st_l_norm` | `ak_acc_st_r_norm` | Subtalar accessory |
| `ak_op_notes` | — | OP notes (TextArea) |

### Ankle — 06 Muscle (`ankle_tables.py`)

| Left field | Right field | Notes |
|---|---|---|
| `ak_str_df_l` | `ak_str_df_r` | Dorsiflexion (TA) strength |
| `ak_str_pf_l` | `ak_str_pf_r` | Plantarflexion (GS) strength |
| `ak_str_ev_l` | `ak_str_ev_r` | Eversion (peroneals) strength |
| `mu_ak_notes` | — | Muscle notes (TextArea) |

### Ankle — 08 Special Tests (YAML-driven, KB key in parentheses)

| Left field | Right field | KB key | Test |
|---|---|---|---|
| `st_ak_ant_draw_l` | `st_ak_ant_draw_r` | `ak_ant_draw` | Ankle Ant Drawer (ATFL) |
| `st_ak_talar_tilt_l` | `st_ak_talar_tilt_r` | `ak_talar_tilt` | Talar Tilt (CFL) |
| `st_ak_thompson_l` | `st_ak_thompson_r` | `ak_thompson` | Thompson (Achilles rupture) |
| `st_ak_royal_london_l` | `st_ak_royal_london_r` | `ak_royal_london` | Royal London (tendinopathy) |
| `st_ak_heel_raise_l` | `st_ak_heel_raise_r` | `ak_heel_raise` | Heel Raise (calf endurance) |
| `st_ak_squeeze_l` | `st_ak_squeeze_r` | `ak_squeeze` | Squeeze (syndesmosis) |
| `st_ak_er_stress_l` | `st_ak_er_stress_r` | `ak_er_stress` | ER Stress (syndesmosis) |
| `st_ak_cotton_l` | `st_ak_cotton_r` | `ak_cotton` | Cotton Test (mortise) |
| `st_ak_ott_lat_mal_l` | `st_ak_ott_lat_mal_r` | `ak_ott_lat_mal` | Ottawa: Lat Malleolus |
| `st_ak_ott_med_mal_l` | `st_ak_ott_med_mal_r` | `ak_ott_med_mal` | Ottawa: Med Malleolus |
| `st_ak_ott_nav_l` | `st_ak_ott_nav_r` | `ak_ott_nav` | Ottawa: Navicular |
| `st_ak_ott_5mt_l` | `st_ak_ott_5mt_r` | `ak_ott_5mt` | Ottawa: 5th Met Base |
| `st_ak_per_prov_l` | `st_ak_per_prov_r` | `ak_per_prov` | Peroneal Provocation |
| `st_ak_notes` | — | — | Special tests notes (TextArea) |

---

## 09 CRPS (`crps.py`)

Budapest / Valencia clinical diagnostic criteria (IASP 2004 / 2021). All criteria
buttons are FlagButtons (Yes = red flag present, No = safe, blank = not assessed).

### Rule 1 — Disproportionate Pain

| Field | Notes |
|---|---|
| `crps_disp_pain` | FlagButton — pain disproportionate to inciting event |
| `crps_disp_pain_notes` | TextArea — notes |

### Rule 2 — Symptoms (Patient Reported)

| Field | Domain | Notes |
|---|---|---|
| `crps_sx_hyperesth` | Sensory | Hyperesthesia |
| `crps_sx_hyperalg` | Sensory | Hyperalgesia |
| `crps_sx_allodynia` | Sensory | Allodynia |
| `crps_sx_temp_asymm` | Vasomotor | Temperature asymmetry |
| `crps_sx_skin_colour` | Vasomotor | Skin colour changes |
| `crps_sx_colour_asymm` | Vasomotor | Colour asymmetry |
| `crps_sx_oedema` | Sudomotor/Oedema | Oedema |
| `crps_sx_sweat_chng` | Sudomotor/Oedema | Sweating change |
| `crps_sx_sweat_asymm` | Sudomotor/Oedema | Sweating asymmetry |
| `crps_sx_rom_dec` | Motor/Trophic | Decreased ROM |
| `crps_sx_weakness` | Motor/Trophic | Weakness |
| `crps_sx_tremor` | Motor/Trophic | Tremor |
| `crps_sx_dystonia` | Motor/Trophic | Dystonia |
| `crps_sx_trophic` | Motor/Trophic | Trophic changes |
| `crps_sx_notes` | — | TextArea — symptom notes |

### Rule 3 — Signs (Clinician Observed)

| Field | Domain | Notes |
|---|---|---|
| `crps_sg_hyperalg_pp` | Sensory | Hyperalgesia to pinprick |
| `crps_sg_allod_lt` | Sensory | Allodynia to light touch |
| `crps_sg_allod_press` | Sensory | Allodynia to pressure |
| `crps_sg_allod_jt` | Sensory | Allodynia to joint movement |
| `crps_sg_temp_asymm` | Vasomotor | Temperature asymmetry |
| `crps_sg_skin_colour` | Vasomotor | Skin colour changes |
| `crps_sg_colour_asymm` | Vasomotor | Colour asymmetry |
| `crps_sg_oedema` | Sudomotor/Oedema | Oedema |
| `crps_sg_sweat_chng` | Sudomotor/Oedema | Sweating change |
| `crps_sg_sweat_asymm` | Sudomotor/Oedema | Sweating asymmetry |
| `crps_sg_rom_dec` | Motor/Trophic | Decreased ROM |
| `crps_sg_weakness` | Motor/Trophic | Weakness |
| `crps_sg_tremor` | Motor/Trophic | Tremor |
| `crps_sg_dystonia` | Motor/Trophic | Dystonia |
| `crps_sg_trophic` | Motor/Trophic | Trophic changes |
| `crps_sg_notes` | — | TextArea — sign notes |

### Rule 4 — No Other Diagnosis

| Field | Notes |
|---|---|
| `crps_no_alt_dx` | FlagButton — no better diagnosis |
| `crps_no_alt_dx_notes` | TextArea — notes |

### Subtype & Notes

| Field | Notes |
|---|---|
| `crps_subtype` | RadioGroup — `T-I` / `T-II` / `Remit` / `NOS` (stored as label string) |
| `crps_subtype_notes` | TextArea |
| `crps_notes` | TextArea — general notes |

### Two-Point Discrimination, Visualisation, Laterality

| Field | Notes |
|---|---|
| `crps_tpd_notes` | TextArea — two-point discrimination findings |
| `crps_vis_notes` | TextArea — visualisation findings |
| `crps_lat_{row}_{col}` | GridInput — laterality table cell; row ∈ {quick, vanilla, context, abstract}; col ∈ {l_acc, l_speed, r_acc, r_speed}. Total 16 fields. Report appends % (acc) or s (speed) if absent. |
| `crps_lat_notes` | TextArea — laterality notes |

### Derived fields (stored in JSON, not editable)

| Field | Notes |
|---|---|
| `crps_sx_domains_triggered` | int — count of triggered symptom domains (0–4) |
| `crps_sg_domains_triggered` | int — count of triggered sign domains (0–4) |
| `crps_criteria_met` | bool — True when all 4 rules satisfied |

---

## Maintenance Notes

- **This file must be updated whenever a field is added or renamed** in any
  section Python file or form driver YAML.
- Field IDs are permanent once data has been collected — see the note at the
  top of `subj_sleep_pilot.yaml` for the "clean break" policy.
- KB keys that do not match any field in this reference are harmless (the
  lookup simply returns nothing) but represent dead weight.
- Keys for hardcoded sections (Neurological, Sensory, Functional, General)
  are defined in the corresponding Python files under
  `objective/sections/`.
