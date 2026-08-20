"""Search index builder and fuzzy scorer for the jump-search (ctrl+.) feature."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from textual.app import App

# ---------------------------------------------------------------------------
# Data type
# ---------------------------------------------------------------------------

@dataclass
class SearchEntry:
    display: str         # shown in the dropdown row
    match_text: str      # text fuzzy-matched against the query
    section_id: str      # section to navigate to
    anchor_id: str | None   # subsection anchor ID (or None)
    widget_id: str | None   # specific widget to focus (or None)
    kind: Literal["section", "subsection", "field", "content"]


# ---------------------------------------------------------------------------
# Static tables
# ---------------------------------------------------------------------------

_SECTION_SHORT: dict[str, str] = {
    "01_consent":             "Consent",
    "02_subjective":          "Subj",
    "03_medical":             "Medical",
    "04_pain_classification": "Pain",
    "05_outcome_measures":    "Outcomes",
    "06_diagnosis":           "Diagnosis",
    "07_barriers":            "Barriers",
    "08_rx_plan":             "Rx Plan",
    "scratchpad":             "Notes",
    "obj:01_general":         "Obj:General",
    "obj:02_active":          "Obj:Active",
    "obj:03_passive":         "Obj:Passive",
    "obj:04_neurological":    "Obj:Neuro",
    "obj:05_sensory":         "Obj:Sensory",
    "obj:06_muscle":          "Obj:Muscle",
    "obj:07_functional":      "Obj:Functional",
    "obj:08_special":         "Obj:Special",
    "obj:09_crps":            "Obj:CRPS",
}

_SECTION_LABELS: dict[str, str] = {
    "01_consent":             "01 Consent",
    "02_subjective":          "02 Subjective",
    "03_medical":             "03 Medical",
    "04_pain_classification": "04 Pain Classification",
    "05_outcome_measures":    "05 Outcome Measures",
    "06_diagnosis":           "06 Diagnosis",
    "07_barriers":            "07 Barriers",
    "08_rx_plan":             "08 Rx & Plan",
    "scratchpad":             "Notes / Scratchpad",
    "obj:01_general":         "Obj 01 General",
    "obj:02_active":          "Obj 02 Active Movement",
    "obj:03_passive":         "Obj 03 Passive Movement",
    "obj:04_neurological":    "Obj 04 Neurological",
    "obj:05_sensory":         "Obj 05 Sensory",
    "obj:06_muscle":          "Obj 06 Muscle Testing",
    "obj:07_functional":      "Obj 07 Functional",
    "obj:08_special":         "Obj 08 Special Tests",
    "obj:09_crps":            "Obj 09 CRPS",
}

# (section_id, anchor_id, display_label)
_SUBSECTIONS: list[tuple[str, str, str]] = [
    # 02 Subjective
    ("02_subjective", "subj_symptoms",     "Body Chart Symptoms"),
    ("02_subjective", "subj_history",      "History"),
    ("02_subjective", "subj_behaviour",    "Behaviour"),
    ("02_subjective", "subj_management",   "Self-Management"),
    ("02_subjective", "subj_activity",     "Activity & Exercise"),
    ("02_subjective", "subj_work",         "Work"),
    ("02_subjective", "subj_sleep",        "Sleep"),
    ("02_subjective", "subj_24hr",         "24Hr Pattern"),
    ("02_subjective", "subj_psychosocial", "Psychosocial"),
    ("02_subjective", "subj_goals",        "SMART Goals"),
    ("02_subjective", "subj_suicide",      "Suicide / Self-Harm Risk"),
    # 03 Medical
    ("03_medical", "med_comorbidities",    "Comorbidities / PMH"),
    ("03_medical", "med_cardiovascular",   "Cardiovascular Risk"),
    ("03_medical", "med_red_flags",        "Red Flags"),
    ("03_medical", "rf_malignancy",        "Red Flag: Malignancy"),
    ("03_medical", "rf_fracture",          "Red Flag: Fracture"),
    ("03_medical", "rf_infection",         "Red Flag: Infection"),
    ("03_medical", "rf_cauda_equina",      "Red Flag: Cauda Equina Compression"),
    ("03_medical", "rf_spinal_cord",       "Red Flag: Spinal Cord Compression"),
    ("03_medical", "med_differential",     "Differential Diagnosis"),
    ("03_medical", "diff_as",              "Differential: Ankylosing Spondylitis"),
    ("03_medical", "diff_aaa",             "Differential: Aortic Aneurysm"),
    ("03_medical", "diff_vc",              "Differential: Vascular Claudication"),
    ("03_medical", "med_medications",      "Medications"),
    ("03_medical", "med_imaging",          "Imaging"),
    # 04 Pain Classification
    ("04_pain_classification", "pc_inflammatory", "Inflammatory"),
    ("04_pain_classification", "pc_nociceptive",  "Nociceptive"),
    ("04_pain_classification", "pc_neuropathic",  "Neuropathic"),
    ("04_pain_classification", "pc_nociplastic",  "Nociplastic"),
    ("04_pain_classification", "pc_central",      "Central Sensitisation"),
    ("04_pain_classification", "pc_fibromyalgia", "Fibromyalgia"),
    ("04_pain_classification", "pc_bacpap",       "BACPAP LBP Phenotyping"),
    ("04_pain_classification", "pc_summary",      "Pain Classification Summary"),
    # 05 Outcome Measures
    ("05_outcome_measures", "om_psfs",       "PSFS"),
    ("05_outcome_measures", "om_bpi",        "BPI"),
    ("05_outcome_measures", "om_dass",       "DASS"),
    ("05_outcome_measures", "om_phq4",       "PHQ-4"),
    ("05_outcome_measures", "om_pcs",        "PCS"),
    ("05_outcome_measures", "om_pseq",       "PSEQ / PSEQ-2 / PCL-5"),
    ("05_outcome_measures", "om_sleep",      "ISI / Sleep"),
    ("05_outcome_measures", "om_additional", "Additional Measures"),
    ("05_outcome_measures", "om_hypothesis", "Outcome Hypothesis"),
    # 06 Diagnosis — no fixed subsections: the CAL-CP walker is per-workup
    # (runtime-variable count), harvested dynamically in build_index() below
    # rather than listed here statically.
    # 07 Barriers
    ("07_barriers", "br_physical",     "Physical Barriers"),
    ("07_barriers", "br_neuro",        "Neurological Barriers"),
    ("07_barriers", "br_nocip",        "Nociplastic Barriers"),
    ("07_barriers", "br_psych",        "Psychological Barriers"),
    ("07_barriers", "br_sleep",        "Sleep & Social Barriers"),
    ("07_barriers", "br_medical",      "Medical Barriers"),
    ("07_barriers", "br_custom",       "Custom Barriers"),
    # 08 Rx Plan
    ("08_rx_plan", "rp_treatment",     "Treatment Plan"),
    ("08_rx_plan", "rp_session1",      "Session 1"),
    ("08_rx_plan", "rp_day1",          "Day 1 Programme"),
    ("08_rx_plan", "rp_followup",      "Follow-Up"),
    # Objective subsections
    ("obj:01_general", "go_physical",            "General: Physical"),
    ("obj:01_general", "go_posture",             "General: Posture"),
    ("obj:02_active",  "am_lumbar",              "Active: Lumbar ROM"),
    ("obj:02_active",  "am_thoracic",            "Active: Thoracic ROM"),
    ("obj:02_active",  "am_cx_lumbar",           "Active: Cervical ROM"),
    ("obj:02_active",  "am_shoulder",            "Active: Shoulder ROM"),
    ("obj:03_passive", "pm_overpressure",        "Passive: Overpressure"),
    ("obj:03_passive", "pm_paivms",              "Passive: PAIVMs"),
    ("obj:03_passive", "pm_cx_overpressure",     "Passive: Cervical OP"),
    ("obj:03_passive", "pm_cx_paivms",           "Passive: Cervical PAIVMs"),
    ("obj:03_passive", "pm_sh_overpressure",     "Passive: Shoulder OP"),
    ("obj:03_passive", "pm_sh_accessory",        "Passive: GH Accessory Glides"),
    ("obj:03_passive", "pm_sh_acsc",             "Passive: AC/SC Joint"),
    ("obj:04_neurological", "nr_reflexes",       "Neuro: Reflexes"),
    ("obj:04_neurological", "nr_myotomes",       "Neuro: Myotomes"),
    ("obj:04_neurological", "nr_dermatomes",     "Neuro: Dermatomes"),
    ("obj:04_neurological", "nr_neurodynamics",  "Neuro: Neurodynamics"),
    ("obj:04_neurological", "nr_umn",            "Neuro: UMN Signs"),
    ("obj:05_sensory",  "sn_hyposensitivity",    "Sensory: Hyposensitivity"),
    ("obj:05_sensory",  "sn_hypersensitivity",   "Sensory: Hypersensitivity"),
    ("obj:06_muscle",   "ml_length",             "Muscle: Length"),
    ("obj:06_muscle",   "ml_activation",         "Muscle: Activation"),
    ("obj:06_muscle",   "ml_strength_trunk",     "Muscle: Strength (Trunk)"),
    ("obj:06_muscle",   "ml_strength_hip",       "Muscle: Strength (Hip)"),
    ("obj:06_muscle",   "ml_sij",                "Muscle: SIJ Provocation"),
    ("obj:06_muscle",   "ml_cx_neck",            "Muscle: Neck Strength"),
    ("obj:06_muscle",   "ml_sh_length",          "Muscle: Shoulder Length"),
    ("obj:06_muscle",   "ml_sh_activation",      "Muscle: Shoulder Activation"),
    ("obj:06_muscle",   "ml_sh_strength",        "Muscle: Shoulder Strength"),
    ("obj:07_functional", "fn_movement",         "Functional: Movement"),
    ("obj:07_functional", "fn_balance",          "Functional: Balance"),
    ("obj:07_functional", "fn_timed",            "Functional: Timed Capability"),
    ("obj:07_functional", "ft_fm_obs",           "Functional: Functional obs notes"),
    ("obj:07_functional", "ft_fm_custom",        "Functional: Custom functional test"),
    ("obj:08_special",  "st_cervical",           "Special Tests: Cervical"),
    ("obj:08_special",  "st_lumbar",             "Special Tests: Lumbar"),
    ("obj:08_special",  "st_shoulder",           "Special Tests: Shoulder"),
    # Hip
    ("obj:02_active",   "am_hip",                "Active: Hip ROM"),
    ("obj:03_passive",  "pm_hp_overpressure",    "Passive: Hip OP"),
    ("obj:03_passive",  "pm_hp_accessory",       "Passive: Hip Accessory"),
    ("obj:06_muscle",   "ml_hp_strength",        "Muscle: Hip Strength"),
    ("obj:08_special",  "st_hip",                "Special Tests: Hip"),
    # Knee
    ("obj:02_active",   "am_knee",               "Active: Knee ROM"),
    ("obj:03_passive",  "pm_kn_overpressure",    "Passive: Knee OP"),
    ("obj:03_passive",  "pm_kn_accessory",       "Passive: Knee Accessory"),
    ("obj:06_muscle",   "ml_kn_strength",        "Muscle: Knee Strength"),
    ("obj:08_special",  "st_knee",               "Special Tests: Knee"),
    # Ankle
    ("obj:02_active",   "am_ankle",              "Active: Ankle ROM"),
    ("obj:03_passive",  "pm_ak_overpressure",    "Passive: Ankle OP"),
    ("obj:03_passive",  "pm_ak_accessory",       "Passive: Ankle Accessory"),
    ("obj:06_muscle",   "ml_ak_strength",        "Muscle: Ankle Strength"),
    ("obj:08_special",  "st_ankle",              "Special Tests: Ankle"),
    # 09 CRPS
    ("obj:09_crps", "crps_disp",         "CRPS: Disproportionate Pain"),
    ("obj:09_crps", "crps_sx",           "CRPS: Symptoms"),
    ("obj:09_crps", "crps_sg",           "CRPS: Signs"),
    ("obj:09_crps", "crps_no_dx",        "CRPS: No Other Diagnosis"),
    ("obj:09_crps", "crps_summary_hdr",  "CRPS: Criteria Summary"),
    ("obj:09_crps", "crps_subtype_hdr",  "CRPS: Subtype Classification"),
    ("obj:09_crps", "crps_tpd",          "CRPS: Two-Point Discrimination"),
    ("obj:09_crps", "crps_vis",          "CRPS: Visualisation"),
    ("obj:09_crps", "crps_lat",          "CRPS: Laterality"),
]

# Pre-built lookup: (section_id, anchor_id) -> subsection label
_SUBSECTION_LABEL: dict[tuple[str, str], str] = {
    (s, a): lbl for s, a, lbl in _SUBSECTIONS
}

# Extra match aliases for specific subsections (terms not in the label itself)
_SUBSECTION_EXTRA: dict[tuple[str, str], str] = {
    ("04_pain_classification", "pc_fibromyalgia"):
        "Wolfe 2016 fibromyalgia FM WPI widespread pain index symptom severity "
        "SS fatigue cognitive IBS depression criteria duration exclusion",
    ("04_pain_classification", "pc_bacpap"):
        "Nijs 2024 BACPAP LBP phenotyping nociplastic hypersensitivity allodynia "
        "dominant mechanism evoked comorbid probable possible nociceptive neuropathic "
        "static dynamic thermal after-sensations",
}

# widget_id -> (section_id, anchor_id_or_None, human_name)
_FIELD_LABELS: dict[str, tuple[str, str | None, str]] = {
    # 01 Consent
    "preferred_name_input":       ("01_consent", None, "Preferred name"),
    "patient_expectations":       ("01_consent", None, "Patient expectations"),
    "reason_for_attending":       ("01_consent", None, "Reason for attending"),
    "cause_understanding_detail": ("01_consent", None, "Cause understanding"),
    "prognosis_expectations":     ("01_consent", None, "Prognosis expectations"),
    "treatment_preference":       ("01_consent", None, "Treatment preference"),
    "belief_notes":               ("01_consent", "cs_beliefs", "Beliefs notes"),
    # 02 Subjective — History
    "onset":              ("02_subjective", "subj_history",    "Onset"),
    "duration":           ("02_subjective", "subj_history",    "Duration"),
    "context_at_onset":   ("02_subjective", "subj_history",    "Context at onset"),
    "previous_episodes":  ("02_subjective", "subj_history",    "Previous episodes"),
    "previous_treatment": ("02_subjective", "subj_history",    "Previous treatment"),
    # 02 Subjective — Behaviour
    "behaviour_boom_bust_text":  ("02_subjective", "subj_behaviour", "Boom-Bust"),
    "behaviour_avoidance_text":  ("02_subjective", "subj_behaviour", "Avoidance"),
    "behaviour_endurance_text":  ("02_subjective", "subj_behaviour", "Endurance"),
    "behaviour_flareups_text":   ("02_subjective", "subj_behaviour", "Flare-ups"),
    # 02 Subjective — Management
    "pain_control_score":    ("02_subjective", "subj_management", "Pain control score"),
    "flareup_prevention":    ("02_subjective", "subj_management", "Flare-up prevention"),
    "management_strategies": ("02_subjective", "subj_management", "Management strategies"),
    "confidence_score":      ("02_subjective", "subj_management", "Confidence score"),
    # 02 Subjective — Activity
    "pre_activity_level":     ("02_subjective", "subj_activity", "Pre-injury activity"),
    "current_activity_level": ("02_subjective", "subj_activity", "Current activity"),
    "exercise_type":          ("02_subjective", "subj_activity", "Exercise type"),
    "exercise_dose":          ("02_subjective", "subj_activity", "Exercise dose"),
    "exercise_response":      ("02_subjective", "subj_activity", "Exercise response"),
    # 02 Subjective — Work
    "pre_injury_role":    ("02_subjective", "subj_work", "Pre-injury role"),
    "pre_injury_hours":   ("02_subjective", "subj_work", "Pre-injury hours"),
    "pre_injury_duties":  ("02_subjective", "subj_work", "Pre-injury duties"),
    "current_work_status":("02_subjective", "subj_work", "Current work status"),
    "current_hours":      ("02_subjective", "subj_work", "Current hours"),
    "current_duties":     ("02_subjective", "subj_work", "Current duties"),
    # 02 Subjective — Sleep (YAML pilot)
    "sleep_overall_rating":    ("02_subjective", "subj_sleep", "Sleep quality rating"),
    "sleep_feels_rested":      ("02_subjective", "subj_sleep", "Feels rested"),
    "sleep_time_to_bed":       ("02_subjective", "subj_sleep", "Time to bed"),
    "sleep_time_attempt":      ("02_subjective", "subj_sleep", "Time attempting sleep"),
    "sleep_onset_time":        ("02_subjective", "subj_sleep", "Time to actual sleep (SOL)"),
    "sleep_waso_clock":        ("02_subjective", "subj_sleep", "Wake after sleep onset — time"),
    "sleep_waso_duration":     ("02_subjective", "subj_sleep", "Wake after sleep onset — length"),
    "sleep_awake_in_bed":      ("02_subjective", "subj_sleep", "Time awake in bed"),
    "sleep_awake_out_bed":     ("02_subjective", "subj_sleep", "Time awake out of bed"),
    "sleep_final_wakeup":      ("02_subjective", "subj_sleep", "Final wake up"),
    "sleep_time_out_of_bed":   ("02_subjective", "subj_sleep", "Time out of bed"),
    "sleep_postural_factors":  ("02_subjective", "subj_sleep", "Sleep postural factors"),
    "sleep_environment_quality":("02_subjective","subj_sleep", "Sleep environment quality"),
    "sleep_daytime_naps":      ("02_subjective", "subj_sleep", "Daytime naps"),
    "sleep_overall_comments":  ("02_subjective", "subj_sleep", "Sleep overall comments"),
    # 02 Subjective — 24hr
    "hr24_am":               ("02_subjective", "subj_24hr", "AM pattern"),
    "hr24_day":              ("02_subjective", "subj_24hr", "Daytime pattern"),
    "hr24_pm":               ("02_subjective", "subj_24hr", "PM pattern"),
    "hr24_nocte":            ("02_subjective", "subj_24hr", "Night (nocte) pattern"),
    "energy_levels":         ("02_subjective", "subj_24hr", "Energy levels"),
    "daily_pattern_comments":("02_subjective", "subj_24hr", "Daily pattern comments"),
    # 02 Subjective — Psychosocial
    "mood_text":               ("02_subjective", "subj_psychosocial", "Mood (text)"),
    "social_situation":        ("02_subjective", "subj_psychosocial", "Social situation"),
    "financial_status":        ("02_subjective", "subj_psychosocial", "Financial status"),
    "cultural_considerations": ("02_subjective", "subj_psychosocial", "Cultural considerations"),
    "psychological_distress":  ("02_subjective", "subj_psychosocial", "Psychological distress"),
    "screening_tool":          ("02_subjective", "subj_psychosocial", "Screening tool"),
    # 02 Subjective — Suicide risk
    "harm_plan":   ("02_subjective", "subj_suicide", "Self-harm plan"),
    "harm_means":  ("02_subjective", "subj_suicide", "Self-harm means"),
    "harm_intent": ("02_subjective", "subj_suicide", "Self-harm intent"),
    "harm_action": ("02_subjective", "subj_suicide", "Self-harm action taken"),
    # 03 Medical
    "previous_injuries":     ("03_medical", "med_comorbidities",  "Previous injuries"),
    "comorbid_other":        ("03_medical", "med_comorbidities",  "Other comorbidities"),
    "rf_malignancy_comment": ("03_medical", "med_red_flags",      "Malignancy comment"),
    "rf_fracture_comment":   ("03_medical", "med_red_flags",      "Fracture comment"),
    "rf_infection_comment":  ("03_medical", "med_red_flags",      "Infection comment"),
    "cauda_equina_action":   ("03_medical", "med_red_flags",      "Cauda equina action"),
    "spinal_cord_action":    ("03_medical", "med_red_flags",      "Spinal cord action"),
    "diff_as_action":        ("03_medical", "med_differential",   "Ankylosing spondylitis action"),
    "diff_aaa_action":       ("03_medical", "med_differential",   "AAA action"),
    "diff_vc_action":        ("03_medical", "med_differential",   "Vascular claudication action"),
    "img_xray_detail":       ("03_medical", "med_imaging",        "Imaging: X-ray detail"),
    "img_us_detail":         ("03_medical", "med_imaging",        "Imaging: Ultrasound detail"),
    "img_ct_detail":         ("03_medical", "med_imaging",        "Imaging: CT detail"),
    "img_mri_detail":        ("03_medical", "med_imaging",        "Imaging: MRI detail"),
    "img_ncs_detail":        ("03_medical", "med_imaging",        "Imaging: NCS detail"),
    "img_other_detail":      ("03_medical", "med_imaging",        "Imaging: Other detail"),
    # 04 Pain Classification
    "noci_interpretation":  ("04_pain_classification", "pc_nociceptive",  "Nociceptive interpretation"),
    "neuro_interpretation": ("04_pain_classification", "pc_neuropathic",  "Neuropathic interpretation"),
    "nocip_interpretation": ("04_pain_classification", "pc_nociplastic",  "Nociplastic interpretation"),
    "csi_score":            ("04_pain_classification", "pc_central",      "CSI score"),
    "fm_wpi":               ("04_pain_classification", "pc_fibromyalgia", "FM: WPI score"),
    "fm_fatigue":           ("04_pain_classification", "pc_fibromyalgia", "FM: Fatigue severity"),
    "fm_waking":            ("04_pain_classification", "pc_fibromyalgia", "FM: Waking unrefreshed"),
    "fm_cognitive":         ("04_pain_classification", "pc_fibromyalgia", "FM: Cognitive symptoms"),
    "bacpap_notes":         ("04_pain_classification", "pc_bacpap",       "BACPAP: Notes"),
    "summary_contributing": ("04_pain_classification", "pc_summary",      "Contributing factors"),
    "summary_reasoning":    ("04_pain_classification", "pc_summary",      "Classification reasoning"),
    # 05 Outcome Measures
    "psfs_act_1":       ("05_outcome_measures", "om_psfs", "PSFS activity 1"),
    "psfs_act_1_score": ("05_outcome_measures", "om_psfs", "PSFS activity 1 score"),
    "psfs_act_2":       ("05_outcome_measures", "om_psfs", "PSFS activity 2"),
    "psfs_act_2_score": ("05_outcome_measures", "om_psfs", "PSFS activity 2 score"),
    "psfs_act_3":       ("05_outcome_measures", "om_psfs", "PSFS activity 3"),
    "psfs_act_3_score": ("05_outcome_measures", "om_psfs", "PSFS activity 3 score"),
    "bpi_activity":  ("05_outcome_measures", "om_bpi",        "BPI: Activity"),
    "bpi_mood":      ("05_outcome_measures", "om_bpi",        "BPI: Mood"),
    "bpi_walking":   ("05_outcome_measures", "om_bpi",        "BPI: Walking"),
    "bpi_work":      ("05_outcome_measures", "om_bpi",        "BPI: Work"),
    "bpi_relations": ("05_outcome_measures", "om_bpi",        "BPI: Relations"),
    "bpi_sleep":     ("05_outcome_measures", "om_bpi",        "BPI: Sleep"),
    "bpi_enjoyment": ("05_outcome_measures", "om_bpi",        "BPI: Enjoyment"),
    "dass_dep_score": ("05_outcome_measures", "om_dass",      "DASS: Depression"),
    "dass_anx_score": ("05_outcome_measures", "om_dass",      "DASS: Anxiety"),
    "dass_str_score": ("05_outcome_measures", "om_dass",      "DASS: Stress"),
    "pcs_rum_score":  ("05_outcome_measures", "om_pcs",       "PCS: Rumination"),
    "pcs_mag_score":  ("05_outcome_measures", "om_pcs",       "PCS: Magnification"),
    "pcs_help_score": ("05_outcome_measures", "om_pcs",       "PCS: Helplessness"),
    "pcs_total_score":("05_outcome_measures", "om_pcs",       "PCS: Total"),
    "pseq_score":     ("05_outcome_measures", "om_pseq",  "PSEQ score"),
    "pseq_interp":    ("05_outcome_measures", "om_pseq",  "PSEQ interpretation"),
    "pseq2_score":    ("05_outcome_measures", "om_pseq",  "PSEQ-2 score"),
    "pseq2_interp":   ("05_outcome_measures", "om_pseq",  "PSEQ-2 interpretation"),
    "phq4_nervous":   ("05_outcome_measures", "om_phq4",  "PHQ-4: Nervous"),
    "phq4_worry":     ("05_outcome_measures", "om_phq4",  "PHQ-4: Worry"),
    "phq4_noint":     ("05_outcome_measures", "om_phq4",  "PHQ-4: No interest"),
    "phq4_depressed": ("05_outcome_measures", "om_phq4",  "PHQ-4: Depressed"),
    "pcl5_score":     ("05_outcome_measures", "om_pseq",  "PCL-5 score"),
    "pcl5_action":    ("05_outcome_measures", "om_pseq",  "PCL-5 action"),
    "isi_score":     ("05_outcome_measures", "om_sleep",      "ISI score"),
    "pbas_score":    ("05_outcome_measures", "om_sleep",      "PBAS score"),
    "add_audit":     ("05_outcome_measures", "om_additional", "AUDIT administered"),
    "add_dudit":     ("05_outcome_measures", "om_additional", "DUDIT administered"),
    "add_epoc":      ("05_outcome_measures", "om_additional", "EPOC notes"),
    "add_other":     ("05_outcome_measures", "om_additional", "Other measures notes"),
    "plan_psfs":     ("05_outcome_measures", "om_psfs",       "Plan: PSFS"),
    "plan_bpi":      ("05_outcome_measures", "om_bpi",        "Plan: BPI"),
    "plan_dass":     ("05_outcome_measures", "om_dass",  "Plan: DASS-21"),
    "plan_phq4":     ("05_outcome_measures", "om_phq4", "Plan: PHQ-4"),
    "plan_pcs":      ("05_outcome_measures", "om_pcs",  "Plan: PCS"),
    "plan_pseq":     ("05_outcome_measures", "om_pseq",       "Plan: PSEQ"),
    "plan_pcl5":     ("05_outcome_measures", "om_pseq",       "Plan: PCL-5"),
    "plan_sleep":    ("05_outcome_measures", "om_sleep",      "Plan: Sleep measures"),
    "plan_additional":("05_outcome_measures","om_additional", "Plan: Additional measures"),
    # 06 Diagnosis — no static entries: the CAL-CP walker's fields are
    # per-workup (runtime-variable count/ids), harvested dynamically in
    # build_index() below instead (see the "CAL-CP diagnosis workups" block).
    "goal_1":             ("02_subjective", "subj_goals",     "Goal 1"),
    "goal_2":             ("02_subjective", "subj_goals",     "Goal 2"),
    "goal_3":             ("02_subjective", "subj_goals",     "Goal 3"),
    "goal_4":             ("02_subjective", "subj_goals",     "Goal 4"),
    # 07 Barriers
    "bi_movement_region": ("07_barriers", "br_physical",  "Movement region"),
    "bi_strength_other":  ("07_barriers", "br_physical",  "Other strength deficit"),
    "bi_deep_other":      ("07_barriers", "br_physical",  "Other deep stability deficit"),
    "bi_over_other":      ("07_barriers", "br_physical",  "Other overactivity"),
    "bi_nerve_region":    ("07_barriers", "br_neuro",     "Nerve region"),
    "bi_red_flag_detail": ("07_barriers", "br_medical",   "Red flag detail"),
    "bi_substance_detail":("07_barriers", "br_medical",   "Substance detail"),
    "custom_1_barrier":   ("07_barriers", "br_custom",    "Custom barrier 1"),
    "custom_1_strategy":  ("07_barriers", "br_custom",    "Custom strategy 1"),
    "custom_2_barrier":   ("07_barriers", "br_custom",    "Custom barrier 2"),
    "custom_2_strategy":  ("07_barriers", "br_custom",    "Custom strategy 2"),
    # 08 Rx Plan
    "tx_goal_orientation":("08_rx_plan", "rp_treatment",  "Goal orientation"),
    "tx_formulation":     ("08_rx_plan", "rp_treatment",  "Treatment formulation"),
    "tx_program":         ("08_rx_plan", "rp_treatment",  "Treatment program"),
    "tx_home_program":    ("08_rx_plan", "rp_treatment",  "Home program"),
    "tx_psychosocial":    ("08_rx_plan", "rp_treatment",  "Psychosocial treatment"),
    "tx_medical":         ("08_rx_plan", "rp_treatment",  "Medical treatment"),
    "tx_rtw":             ("08_rx_plan", "rp_treatment",  "Return to work plan"),
    "s1_education":       ("08_rx_plan", "rp_session1",   "Session 1: Education"),
    "s1_experiential":    ("08_rx_plan", "rp_session1",   "Session 1: Experiential"),
    "s1_confidence_nrs":  ("08_rx_plan", "rp_session1",   "Session 1: Confidence NRS"),
    "s1_hw_other":        ("08_rx_plan", "rp_session1",   "Session 1: HW other"),
    "fu_next_focus":      ("08_rx_plan", "rp_followup",   "Follow-up: Next focus"),
    "fu_monitoring":      ("08_rx_plan", "rp_followup",   "Follow-up: Monitoring"),
    "fu_om_schedule":     ("08_rx_plan", "rp_followup",   "Follow-up: OM schedule"),
    # Scratchpad
    "scratchpad_text": ("scratchpad", None, "Scratchpad notes"),
}

# Assessment sections to harvest button widgets from (objective excluded)
_ASSESSMENT_SECTION_IDS = [
    "01_consent", "02_subjective", "03_medical", "04_pain_classification",
    "05_outcome_measures", "06_diagnosis", "07_barriers", "08_rx_plan", "scratchpad",
]

# Objective KB-linked fields — (widget_id, region, section_id, human_name, extra_match)
# Mostly special tests (st_ prefix, SpecialTestsWidget._rg_id pattern), but also any
# other objective field clinical_kb.db's test_field_map points at (e.g. ROM values
# that are themselves a CPR cluster member, like Cervical Rotation ROM for Wainner
# CPR) — validate_kb.py hard-fails on any test_field_map pab_field_id missing here.
_OBJ_KB_FIELDS: list[tuple[str, str, str, str, str]] = [
    # ── Cervical ──────────────────────────────────────────────────────────────
    ("st_spurling_l",      "cervical", "obj:08_special", "Spurling's Left",           "foraminal compression radiculopathy arm pain"),
    ("st_spurling_r",      "cervical", "obj:08_special", "Spurling's Right",          "foraminal compression radiculopathy arm pain"),
    ("st_distraction_l",   "cervical", "obj:08_special", "Cervical Distraction L",    "radiculopathy IVF foraminal relief"),
    ("st_distraction_r",   "cervical", "obj:08_special", "Cervical Distraction R",    "radiculopathy IVF foraminal relief"),
    ("st_ulnt1_l",         "cervical", "obj:08_special", "ULNT1 Left",                "upper limb tension median nerve neurodynamic"),
    ("st_ulnt1_r",         "cervical", "obj:08_special", "ULNT1 Right",               "upper limb tension median nerve neurodynamic"),
    ("st_ulnt2a_l",        "cervical", "obj:08_special", "ULNT2a Left",               "radial nerve neurodynamic upper limb tension"),
    ("st_ulnt2a_r",        "cervical", "obj:08_special", "ULNT2a Right",              "radial nerve neurodynamic upper limb tension"),
    ("st_ulnt3_l",         "cervical", "obj:08_special", "ULNT3 Left",                "ulnar nerve neurodynamic upper limb tension"),
    ("st_ulnt3_r",         "cervical", "obj:08_special", "ULNT3 Right",               "ulnar nerve neurodynamic upper limb tension"),
    ("st_frt_l",           "cervical", "obj:08_special", "FRT Left",                  "flexion rotation test cervicogenic headache CGH C1 C2"),
    ("st_frt_r",           "cervical", "obj:08_special", "FRT Right",                 "flexion rotation test cervicogenic headache CGH"),
    ("st_sharp_purser_l",  "cervical", "obj:08_special", "Sharp-Purser L",            "upper cervical instability atlantoaxial"),
    ("st_sharp_purser_r",  "cervical", "obj:08_special", "Sharp-Purser R",            "upper cervical instability atlantoaxial"),
    ("st_ant_shear_l",     "cervical", "obj:08_special", "Anterior Shear L",          "upper cervical instability transverse ligament"),
    ("st_ant_shear_r",     "cervical", "obj:08_special", "Anterior Shear R",          "upper cervical instability transverse ligament"),
    ("st_alar_sf_l",       "cervical", "obj:08_special", "Alar Ligament SF L",        "upper cervical instability alar"),
    ("st_alar_sf_r",       "cervical", "obj:08_special", "Alar Ligament SF R",        "upper cervical instability alar"),
    ("st_alar_rot_l",      "cervical", "obj:08_special", "Alar Ligament Rotation L",  "upper cervical instability alar ligament rotation stress"),
    ("st_alar_rot_r",      "cervical", "obj:08_special", "Alar Ligament Rotation R",  "upper cervical instability alar ligament rotation stress"),
    ("st_lat_trans_l",     "cervical", "obj:08_special", "Lateral Translation L",     "upper cervical instability lateral stability"),
    ("st_lat_trans_r",     "cervical", "obj:08_special", "Lateral Translation R",     "upper cervical instability lateral stability"),
    ("st_vbi_sus_rot_l",   "cervical", "obj:08_special", "VBI Sustained Rotation L",  "vertebrobasilar insufficiency pre-manipulation screen"),
    ("st_vbi_sus_rot_r",   "cervical", "obj:08_special", "VBI Sustained Rotation R",  "vertebrobasilar insufficiency pre-manipulation screen"),
    ("st_ccft_l",          "cervical", "obj:08_special", "CCFT",                      "cranio-cervical flexion test deep cervical flexor motor control cervicogenic headache"),
    ("st_ccft_r",          "cervical", "obj:08_special", "CCFT (R, unused)",          "cranio-cervical flexion test deep cervical flexor motor control cervicogenic headache"),
    # ── Neurological — UMN signs (myelopathy screen) ─────────────────────────────
    ("nr_umn_hoffman",     "neurological", "obj:04_neurological", "Hoffman's",        "myelopathy UMN upper motor neuron corticospinal"),
    ("nr_umn_tromner",     "neurological", "obj:04_neurological", "Tromner",          "myelopathy UMN upper motor neuron corticospinal"),
    ("nr_umn_bab",         "neurological", "obj:04_neurological", "Babinski",         "myelopathy UMN upper motor neuron corticospinal"),
    ("nr_umn_lhermitte",   "neurological", "obj:04_neurological", "Lhermitte's",      "myelopathy UMN electric shock spine flexion"),
    ("nr_umn_inv_sup",     "neurological", "obj:04_neurological", "Inverted Supinator", "myelopathy UMN inverted radial reflex"),
    ("cx_rot_ax_l_range",  "cervical", "obj:02_active", "Cervical Rotation ROM (L)", "wainner CPR radiculopathy involved side rotation"),
    ("cx_rot_ax_r_range",  "cervical", "obj:02_active", "Cervical Rotation ROM (R)", "wainner CPR radiculopathy involved side rotation"),
    # ── Lumbar ────────────────────────────────────────────────────────────────
    ("st_slr_l",         "lumbar",   "obj:08_special", "SLR Left",                  "straight leg raise sciatic radiculopathy disc herniation"),
    ("st_slr_r",         "lumbar",   "obj:08_special", "SLR Right",                 "straight leg raise sciatic radiculopathy disc herniation"),
    ("st_slump_l",       "lumbar",   "obj:08_special", "Slump Left",                "neurodynamic sciatic lumbar radiculopathy"),
    ("st_slump_r",       "lumbar",   "obj:08_special", "Slump Right",               "neurodynamic sciatic lumbar radiculopathy"),
    ("st_femoral_l",     "lumbar",   "obj:08_special", "Femoral Stretch Left",      "femoral nerve L2 L3 L4 radiculopathy"),
    ("st_femoral_r",     "lumbar",   "obj:08_special", "Femoral Stretch Right",     "femoral nerve L2 L3 L4 radiculopathy"),
    ("st_faber_l",       "lumbar",   "obj:08_special", "FABER Left",                "Patrick hip SIJ sacroiliac joint"),
    ("st_faber_r",       "lumbar",   "obj:08_special", "FABER Right",               "Patrick hip SIJ sacroiliac joint"),
    ("st_fadir_l",       "lumbar",   "obj:08_special", "FADIR Left",                "hip impingement FAI labral acetabular"),
    ("st_fadir_r",       "lumbar",   "obj:08_special", "FADIR Right",               "hip impingement FAI labral acetabular"),
    ("st_prone_inst_l",  "lumbar",   "obj:08_special", "Prone Instability Left",    "lumbar instability segmental"),
    ("st_prone_inst_r",  "lumbar",   "obj:08_special", "Prone Instability Right",   "lumbar instability segmental"),
    ("st_crossed_slr_l", "lumbar",   "obj:08_special", "Crossed SLR Left",          "disc herniation central paracentral contralateral"),
    ("st_crossed_slr_r", "lumbar",   "obj:08_special", "Crossed SLR Right",         "disc herniation central paracentral contralateral"),
    # ── Shoulder ─────────────────────────────────────────────────────────────
    ("st_hawkins_l",      "shoulder", "obj:08_special", "Hawkins-Kennedy Left",      "impingement subacromial coracoacromial supraspinatus"),
    ("st_hawkins_r",      "shoulder", "obj:08_special", "Hawkins-Kennedy Right",     "impingement subacromial coracoacromial supraspinatus"),
    ("st_neer_l",         "shoulder", "obj:08_special", "Neer Sign Left",            "impingement subacromial acromion supraspinatus"),
    ("st_neer_r",         "shoulder", "obj:08_special", "Neer Sign Right",           "impingement subacromial acromion supraspinatus"),
    ("st_painful_arc_l",  "shoulder", "obj:08_special", "Painful Arc Left",          "impingement subacromial 60 120 abduction"),
    ("st_painful_arc_r",  "shoulder", "obj:08_special", "Painful Arc Right",         "impingement subacromial 60 120 abduction"),
    ("st_empty_can_l",    "shoulder", "obj:08_special", "Empty Can Left",            "supraspinatus rotator cuff tear Jobe scapular plane"),
    ("st_empty_can_r",    "shoulder", "obj:08_special", "Empty Can Right",           "supraspinatus rotator cuff tear Jobe scapular plane"),
    ("st_full_can_l",     "shoulder", "obj:08_special", "Full Can Left",             "supraspinatus rotator cuff strength scapular plane"),
    ("st_full_can_r",     "shoulder", "obj:08_special", "Full Can Right",            "supraspinatus rotator cuff strength scapular plane"),
    ("st_er_lag_l",       "shoulder", "obj:08_special", "ER Lag Sign Left",          "infraspinatus external rotation lag full thickness tear"),
    ("st_er_lag_r",       "shoulder", "obj:08_special", "ER Lag Sign Right",         "infraspinatus external rotation lag full thickness tear"),
    ("st_lift_off_l",     "shoulder", "obj:08_special", "Lift-off Left",             "subscapularis Gerber internal rotation behind back"),
    ("st_lift_off_r",     "shoulder", "obj:08_special", "Lift-off Right",            "subscapularis Gerber internal rotation behind back"),
    ("st_belly_press_l",  "shoulder", "obj:08_special", "Belly Press Left",          "subscapularis Napoleon internal rotation wrist"),
    ("st_belly_press_r",  "shoulder", "obj:08_special", "Belly Press Right",         "subscapularis Napoleon internal rotation wrist"),
    ("st_drop_arm_l",     "shoulder", "obj:08_special", "Drop Arm Left",             "full thickness rotator cuff tear supraspinatus eccentric"),
    ("st_drop_arm_r",     "shoulder", "obj:08_special", "Drop Arm Right",            "full thickness rotator cuff tear supraspinatus eccentric"),
    ("st_cross_body_l",   "shoulder", "obj:08_special", "Cross-body Adduction Left", "AC joint acromioclavicular horizontal adduction"),
    ("st_cross_body_r",   "shoulder", "obj:08_special", "Cross-body Adduction Right","AC joint acromioclavicular horizontal adduction"),
    ("st_ac_stress_l",    "shoulder", "obj:08_special", "AC Stress Left",            "acromioclavicular joint stress compression shear"),
    ("st_ac_stress_r",    "shoulder", "obj:08_special", "AC Stress Right",           "acromioclavicular joint stress compression shear"),
    ("st_speeds_l",       "shoulder", "obj:08_special", "Speed's Left",              "biceps tendinopathy SLAP long head bicipital groove"),
    ("st_speeds_r",       "shoulder", "obj:08_special", "Speed's Right",             "biceps tendinopathy SLAP long head bicipital groove"),
    ("st_yergason_l",     "shoulder", "obj:08_special", "Yergason's Left",           "bicipital tendinopathy groove instability supination"),
    ("st_yergason_r",     "shoulder", "obj:08_special", "Yergason's Right",          "bicipital tendinopathy groove instability supination"),
    ("st_obrien_l",       "shoulder", "obj:08_special", "O'Brien Left",              "SLAP tear active compression AC joint deep pain"),
    ("st_obrien_r",       "shoulder", "obj:08_special", "O'Brien Right",             "SLAP tear active compression AC joint deep pain"),
    ("st_apprehension_l", "shoulder", "obj:08_special", "Apprehension Left",         "anterior instability glenohumeral dislocation ER"),
    ("st_apprehension_r", "shoulder", "obj:08_special", "Apprehension Right",        "anterior instability glenohumeral dislocation ER"),
    ("st_relocation_l",   "shoulder", "obj:08_special", "Relocation Left",           "anterior instability Jobe posterior force humeral head"),
    ("st_relocation_r",   "shoulder", "obj:08_special", "Relocation Right",          "anterior instability Jobe posterior force humeral head"),
    ("st_sulcus_l",       "shoulder", "obj:08_special", "Sulcus Sign Left",          "inferior instability MDI multidirectional traction"),
    ("st_sulcus_r",       "shoulder", "obj:08_special", "Sulcus Sign Right",         "inferior instability MDI multidirectional traction"),
    ("st_scap_assist_l",  "shoulder", "obj:08_special", "Scap Assist Left",          "scapular dyskinesis upward rotation posterior tilt SA LT"),
    ("st_scap_assist_r",  "shoulder", "obj:08_special", "Scap Assist Right",         "scapular dyskinesis upward rotation posterior tilt SA LT"),
    ("st_wall_pushup_l",  "shoulder", "obj:08_special", "Wall Push-up Left",         "serratus anterior winging long thoracic nerve"),
    ("st_wall_pushup_r",  "shoulder", "obj:08_special", "Wall Push-up Right",        "serratus anterior winging long thoracic nerve"),
    ("st_er_resist_l",    "shoulder", "obj:08_special", "ER Resistance Left",        "impingement infraspinatus subacromial SIS cluster"),
    ("st_er_resist_r",    "shoulder", "obj:08_special", "ER Resistance Right",       "impingement infraspinatus subacromial SIS cluster"),
    ("st_irls_l",         "shoulder", "obj:08_special", "IR Lag Sign Left",          "subscapularis internal rotation lag full thickness tear"),
    ("st_irls_r",         "shoulder", "obj:08_special", "IR Lag Sign Right",         "subscapularis internal rotation lag full thickness tear"),
    ("st_drop_is_l",      "shoulder", "obj:08_special", "Drop Sign (IS) Left",       "infraspinatus drop sign rotator cuff lag battery"),
    ("st_drop_is_r",      "shoulder", "obj:08_special", "Drop Sign (IS) Right",      "infraspinatus drop sign rotator cuff lag battery"),
    ("st_hornblower_l",   "shoulder", "obj:08_special", "Hornblower's Left",         "teres minor rotator cuff lag battery massive tear"),
    ("st_hornblower_r",   "shoulder", "obj:08_special", "Hornblower's Right",        "teres minor rotator cuff lag battery massive tear"),
    ("st_ac_ext_l",       "shoulder", "obj:08_special", "AC Resisted Extension Left","acromioclavicular joint resisted extension confirm cluster"),
    ("st_ac_ext_r",       "shoulder", "obj:08_special", "AC Resisted Extension Right","acromioclavicular joint resisted extension confirm cluster"),
    ("st_pass_comp_l",    "shoulder", "obj:08_special", "Passive Compression Left",  "SLAP tear labral passive compression Kim"),
    ("st_pass_comp_r",    "shoulder", "obj:08_special", "Passive Compression Right", "SLAP tear labral passive compression Kim"),
    ("st_bicip_groove_l", "shoulder", "obj:08_special", "Bicipital Groove Left",     "biceps tendinopathy palpation groove tenderness"),
    ("st_bicip_groove_r", "shoulder", "obj:08_special", "Bicipital Groove Right",    "biceps tendinopathy palpation groove tenderness"),
    ("st_adson_l",        "shoulder", "obj:08_special", "Adson's Left",              "thoracic outlet syndrome TOS scalene subclavian"),
    ("st_adson_r",        "shoulder", "obj:08_special", "Adson's Right",             "thoracic outlet syndrome TOS scalene subclavian"),
    ("st_roos_l",         "shoulder", "obj:08_special", "Roos/EAST Left",            "thoracic outlet syndrome TOS elevated arm stress test"),
    ("st_roos_r",         "shoulder", "obj:08_special", "Roos/EAST Right",           "thoracic outlet syndrome TOS elevated arm stress test"),
    ("st_wright_l",       "shoulder", "obj:08_special", "Wright's Left",             "thoracic outlet syndrome TOS hyperabduction pectoralis minor"),
    ("st_wright_r",       "shoulder", "obj:08_special", "Wright's Right",            "thoracic outlet syndrome TOS hyperabduction pectoralis minor"),
    ("st_crlf_l",         "shoulder", "obj:08_special", "CRLF Left",                 "cervical rotation lateral flexion TOS rule out cervical spine"),
    ("st_crlf_r",         "shoulder", "obj:08_special", "CRLF Right",                "cervical rotation lateral flexion TOS rule out cervical spine"),
    # ── Hip ──────────────────────────────────────────────────────────────────
    ("st_hp_fadir_l",          "hip", "obj:08_special", "FADIR Left",                "FAI femoroacetabular impingement cam pincer labral anterior groin"),
    ("st_hp_fadir_r",          "hip", "obj:08_special", "FADIR Right",               "FAI femoroacetabular impingement cam pincer labral anterior groin"),
    ("st_hp_ant_imp_l",        "hip", "obj:08_special", "Anterior Impingement Left", "FAI anterior capsule labrum impingement hip"),
    ("st_hp_ant_imp_r",        "hip", "obj:08_special", "Anterior Impingement Right","FAI anterior capsule labrum impingement hip"),
    ("st_hp_faber_l",          "hip", "obj:08_special", "FABER Left",                "Patrick hip OA SIJ sacroiliac joint flexion abduction external rotation"),
    ("st_hp_faber_r",          "hip", "obj:08_special", "FABER Right",               "Patrick hip OA SIJ sacroiliac joint flexion abduction external rotation"),
    ("st_hp_hip_scour_l",      "hip", "obj:08_special", "Hip Scour Left",            "hip OA intra-articular quadrant loading crepitus"),
    ("st_hp_hip_scour_r",      "hip", "obj:08_special", "Hip Scour Right",           "hip OA intra-articular quadrant loading crepitus"),
    ("st_hp_log_roll_l",       "hip", "obj:08_special", "Log Roll Left",             "hip OA synovitis intra-articular passive rotation"),
    ("st_hp_log_roll_r",       "hip", "obj:08_special", "Log Roll Right",            "hip OA synovitis intra-articular passive rotation"),
    ("st_hp_ober_l",           "hip", "obj:08_special", "Ober's Left",               "ITB TFL tightness GTPS lateral hip bursitis"),
    ("st_hp_ober_r",           "hip", "obj:08_special", "Ober's Right",              "ITB TFL tightness GTPS lateral hip bursitis"),
    ("st_hp_trendelenburg_l",  "hip", "obj:08_special", "Trendelenburg Left",        "gluteus medius weakness pelvic stability GTPS abductor"),
    ("st_hp_trendelenburg_r",  "hip", "obj:08_special", "Trendelenburg Right",       "gluteus medius weakness pelvic stability GTPS abductor"),
    ("st_hp_sls_hip_l",        "hip", "obj:08_special", "SLS Hip Left",              "single leg stance balance abductor load control lateral"),
    ("st_hp_sls_hip_r",        "hip", "obj:08_special", "SLS Hip Right",             "single leg stance balance abductor load control lateral"),
    ("st_hp_puranen_orava_l",  "hip", "obj:08_special", "Puranen-Orava Left",        "proximal hamstring tendinopathy ischial tuberosity stretch"),
    ("st_hp_puranen_orava_r",  "hip", "obj:08_special", "Puranen-Orava Right",       "proximal hamstring tendinopathy ischial tuberosity stretch"),
    ("st_hp_bks_l",            "hip", "obj:08_special", "Bent Knee Stretch Left",    "proximal hamstring tendinopathy BKS prone knee flex ischial"),
    ("st_hp_bks_r",            "hip", "obj:08_special", "Bent Knee Stretch Right",   "proximal hamstring tendinopathy BKS prone knee flex ischial"),
    ("st_hp_squeeze_l",        "hip", "obj:08_special", "Squeeze Test Left",         "adductor groin pain osteitis pubis athletic pubalgia isometric"),
    ("st_hp_squeeze_r",        "hip", "obj:08_special", "Squeeze Test Right",        "adductor groin pain osteitis pubis athletic pubalgia isometric"),
    # ── Knee ─────────────────────────────────────────────────────────────────
    ("st_kn_lachman_l",   "knee", "obj:08_special", "Lachman Left",                  "ACL anterior cruciate ligament Lachman anterior translation endpoint"),
    ("st_kn_lachman_r",   "knee", "obj:08_special", "Lachman Right",                 "ACL anterior cruciate ligament Lachman anterior translation endpoint"),
    ("st_kn_ant_draw_l",  "knee", "obj:08_special", "Anterior Drawer Knee Left",     "ACL anterior drawer 90 degrees tibial translation"),
    ("st_kn_ant_draw_r",  "knee", "obj:08_special", "Anterior Drawer Knee Right",    "ACL anterior drawer 90 degrees tibial translation"),
    ("st_kn_pivot_l",     "knee", "obj:08_special", "Pivot Shift Left",              "ACL rotatory instability anterolateral subluxation clunk"),
    ("st_kn_pivot_r",     "knee", "obj:08_special", "Pivot Shift Right",             "ACL rotatory instability anterolateral subluxation clunk"),
    ("st_kn_post_draw_l", "knee", "obj:08_special", "Posterior Drawer Left",         "PCL posterior cruciate ligament posterior tibial translation"),
    ("st_kn_post_draw_r", "knee", "obj:08_special", "Posterior Drawer Right",        "PCL posterior cruciate ligament posterior tibial translation"),
    ("st_kn_post_sag_l",  "knee", "obj:08_special", "Posterior Sag Left",            "PCL Godfrey gravity sag posterior tibial subluxation"),
    ("st_kn_post_sag_r",  "knee", "obj:08_special", "Posterior Sag Right",           "PCL Godfrey gravity sag posterior tibial subluxation"),
    ("st_kn_mcmurray_l",  "knee", "obj:08_special", "McMurray's Left",               "meniscus McMurray click clunk medial lateral rotation"),
    ("st_kn_mcmurray_r",  "knee", "obj:08_special", "McMurray's Right",              "meniscus McMurray click clunk medial lateral rotation"),
    ("st_kn_thessaly_l",  "knee", "obj:08_special", "Thessaly Left",                 "meniscus Thessaly functional load rotation standing 20 degrees"),
    ("st_kn_thessaly_r",  "knee", "obj:08_special", "Thessaly Right",                "meniscus Thessaly functional load rotation standing 20 degrees"),
    ("st_kn_jlt_l",       "knee", "obj:08_special", "Joint Line Tenderness Left",    "meniscus JLT palpation medial lateral joint line"),
    ("st_kn_jlt_r",       "knee", "obj:08_special", "Joint Line Tenderness Right",   "meniscus JLT palpation medial lateral joint line"),
    ("st_kn_valgus_0_l",  "knee", "obj:08_special", "Valgus 0° Left",                "MCL medial collateral ligament valgus full extension posterior capsule"),
    ("st_kn_valgus_0_r",  "knee", "obj:08_special", "Valgus 0° Right",               "MCL medial collateral ligament valgus full extension posterior capsule"),
    ("st_kn_valgus_30_l", "knee", "obj:08_special", "Valgus 30° Left",               "MCL medial collateral ligament isolated 30 degree flexion"),
    ("st_kn_valgus_30_r", "knee", "obj:08_special", "Valgus 30° Right",              "MCL medial collateral ligament isolated 30 degree flexion"),
    ("st_kn_varus_0_l",   "knee", "obj:08_special", "Varus 0° Left",                 "LCL lateral collateral ligament varus posterolateral corner"),
    ("st_kn_varus_0_r",   "knee", "obj:08_special", "Varus 0° Right",                "LCL lateral collateral ligament varus posterolateral corner"),
    ("st_kn_varus_30_l",  "knee", "obj:08_special", "Varus 30° Left",                "LCL lateral collateral ligament isolated 30 degree flexion"),
    ("st_kn_varus_30_r",  "knee", "obj:08_special", "Varus 30° Right",               "LCL lateral collateral ligament isolated 30 degree flexion"),
    ("st_kn_clarkes_l",   "knee", "obj:08_special", "Clarke's Left",                 "PFJ patellofemoral pain Clarke grind retropatellar"),
    ("st_kn_clarkes_r",   "knee", "obj:08_special", "Clarke's Right",                "PFJ patellofemoral pain Clarke grind retropatellar"),
    ("st_kn_pat_tilt_l",  "knee", "obj:08_special", "Patella Tilt Left",             "PFJ lateral retinaculum tightness patellofemoral tilt"),
    ("st_kn_pat_tilt_r",  "knee", "obj:08_special", "Patella Tilt Right",            "PFJ lateral retinaculum tightness patellofemoral tilt"),
    ("st_kn_pat_grind_l", "knee", "obj:08_special", "Patella Grind Left",            "PFJ chondromalacia articular cartilage crepitus grind"),
    ("st_kn_pat_grind_r", "knee", "obj:08_special", "Patella Grind Right",           "PFJ chondromalacia articular cartilage crepitus grind"),
    # ── Ankle ────────────────────────────────────────────────────────────────
    ("st_ak_ant_draw_l",     "ankle", "obj:08_special", "Ankle Ant Drawer Left",      "ATFL anterior talofibular ligament sprain lateral ankle instability"),
    ("st_ak_ant_draw_r",     "ankle", "obj:08_special", "Ankle Ant Drawer Right",     "ATFL anterior talofibular ligament sprain lateral ankle instability"),
    ("st_ak_talar_tilt_l",   "ankle", "obj:08_special", "Talar Tilt Left",            "CFL calcaneofibular ligament inversion stress lateral ankle"),
    ("st_ak_talar_tilt_r",   "ankle", "obj:08_special", "Talar Tilt Right",           "CFL calcaneofibular ligament inversion stress lateral ankle"),
    ("st_ak_thompson_l",     "ankle", "obj:08_special", "Thompson Left",              "Achilles tendon rupture complete calf squeeze Simmonds"),
    ("st_ak_thompson_r",     "ankle", "obj:08_special", "Thompson Right",             "Achilles tendon rupture complete calf squeeze Simmonds"),
    ("st_ak_royal_london_l", "ankle", "obj:08_special", "Royal London Left",          "Achilles tendinopathy mid-portion load test palpation pain relief"),
    ("st_ak_royal_london_r", "ankle", "obj:08_special", "Royal London Right",         "Achilles tendinopathy mid-portion load test palpation pain relief"),
    ("st_ak_heel_raise_l",   "ankle", "obj:08_special", "Heel Raise Left",            "calf endurance Achilles tendinopathy single leg reps plantarflexion"),
    ("st_ak_heel_raise_r",   "ankle", "obj:08_special", "Heel Raise Right",           "calf endurance Achilles tendinopathy single leg reps plantarflexion"),
    ("st_ak_squeeze_l",      "ankle", "obj:08_special", "Squeeze Ankle Left",         "syndesmosis tibiofibular fibula compression distal"),
    ("st_ak_squeeze_r",      "ankle", "obj:08_special", "Squeeze Ankle Right",        "syndesmosis tibiofibular fibula compression distal"),
    ("st_ak_er_stress_l",    "ankle", "obj:08_special", "ER Stress Left",             "syndesmosis external rotation stress distal tibiofibular"),
    ("st_ak_er_stress_r",    "ankle", "obj:08_special", "ER Stress Right",            "syndesmosis external rotation stress distal tibiofibular"),
    ("st_ak_cotton_l",       "ankle", "obj:08_special", "Cotton Test Left",           "syndesmosis lateral mortise talar shift mortise widening"),
    ("st_ak_cotton_r",       "ankle", "obj:08_special", "Cotton Test Right",          "syndesmosis lateral mortise talar shift mortise widening"),
    ("st_ak_ott_lat_mal_l",  "ankle", "obj:08_special", "Ottawa Lat Malleolus Left",  "Ottawa Rules fibula posterior tip fracture X-ray criteria"),
    ("st_ak_ott_lat_mal_r",  "ankle", "obj:08_special", "Ottawa Lat Malleolus Right", "Ottawa Rules fibula posterior tip fracture X-ray criteria"),
    ("st_ak_ott_med_mal_l",  "ankle", "obj:08_special", "Ottawa Med Malleolus Left",  "Ottawa Rules tibia medial malleolus fracture X-ray criteria"),
    ("st_ak_ott_med_mal_r",  "ankle", "obj:08_special", "Ottawa Med Malleolus Right", "Ottawa Rules tibia medial malleolus fracture X-ray criteria"),
    ("st_ak_ott_nav_l",      "ankle", "obj:08_special", "Ottawa Navicular Left",      "Ottawa Foot Rules navicular fracture midfoot X-ray"),
    ("st_ak_ott_nav_r",      "ankle", "obj:08_special", "Ottawa Navicular Right",     "Ottawa Foot Rules navicular fracture midfoot X-ray"),
    ("st_ak_ott_5mt_l",      "ankle", "obj:08_special", "Ottawa 5th Met Left",        "Ottawa Foot Rules 5th metatarsal base Jones fracture styloid"),
    ("st_ak_ott_5mt_r",      "ankle", "obj:08_special", "Ottawa 5th Met Right",       "Ottawa Foot Rules 5th metatarsal base Jones fracture styloid"),
    ("st_ak_per_prov_l",     "ankle", "obj:08_special", "Peroneal Provocation Left",  "peroneal tendon subluxation tendinopathy resisted eversion arc"),
    ("st_ak_per_prov_r",     "ankle", "obj:08_special", "Peroneal Provocation Right", "peroneal tendon subluxation tendinopathy resisted eversion arc"),
    # ── Sensory — pain sensitisation screen ──────────────────────────────────────
    ("sn_static_allodynia",  "screening", "obj:05_sensory", "Static Allodynia",         "tactile mechanical allodynia von frey monofilament pain sensitisation"),
    ("sn_pin_prick",         "screening", "obj:05_sensory", "Sharp Hyperalgesia",       "pin prick hyperalgesia toothpick pain sensitisation"),
    ("sn_ppt",               "screening", "obj:05_sensory", "Pressure Hyperalgesia (PPT)", "pressure pain threshold algometer central sensitisation"),
    ("sn_cold",              "screening", "obj:05_sensory", "Cold Hyperalgesia",        "ice pain test cold hyperalgesia thermal pain sensitisation"),
    ("sn_cpm",               "screening", "obj:05_sensory", "Conditioned Pain Modulation", "CPM cold pressor endogenous analgesia descending pain modulation"),
    ("sn_nerve_palpation",   "screening", "obj:05_sensory", "Upper Limb Nerve Trunk Palpation", "median ulnar radial nerve mechanosensitivity neural tissue"),
]


# ---------------------------------------------------------------------------
# Fuzzy scoring
# ---------------------------------------------------------------------------

def fuzzy_score(query: str, target: str) -> int:
    """Return match score > 0 if query fuzzy-matches target. Higher = better."""
    if not query:
        return 0
    q, t = query.lower(), target.lower()
    if q == t:
        return 1000
    if t.startswith(q):
        return 900
    if q in t:
        return 800 - t.index(q)
    # Character subsequence
    idx = 0
    gaps = 0
    for ch in q:
        pos = t.find(ch, idx)
        if pos == -1:
            return 0
        gaps += pos - idx
        idx = pos + 1
    return max(1, 200 - gaps)


def _snippet(text: str, max_len: int = 48) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:max_len] + ("…" if len(line) > max_len else "")
    return ""


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

def build_index(app: "App") -> list[SearchEntry]:
    """Build a fresh search index from live app state."""
    from .assessment_view import AssessmentView
    from .widgets import CheckButton
    from textual.widgets import TextArea, Input as TInput

    entries: list[SearchEntry] = []

    # 1 — Sections
    for sec_id, label in _SECTION_LABELS.items():
        entries.append(SearchEntry(
            display=label,
            match_text=label,
            section_id=sec_id,
            anchor_id=None,
            widget_id=None,
            kind="section",
        ))

    # 2 — Subsections
    for sec_id, anchor_id, label in _SUBSECTIONS:
        short = _SECTION_SHORT.get(sec_id, sec_id)
        extra = _SUBSECTION_EXTRA.get((sec_id, anchor_id), "")
        entries.append(SearchEntry(
            display=f"{short} › {label}",
            match_text=f"{label} {short} {extra}".strip(),
            section_id=sec_id,
            anchor_id=anchor_id,
            widget_id=None,
            kind="subsection",
        ))

    try:
        av = app.query_one("#assessment_view", AssessmentView)
    except Exception:
        return entries

    # 3 — CheckButton / FlagButton labels (assessment sections only)
    for sec_id in _ASSESSMENT_SECTION_IDS:
        section = av.sections.get(sec_id)
        if section is None:
            continue
        short = _SECTION_SHORT.get(sec_id, sec_id)
        try:
            for btn in section.query(CheckButton):
                if not btn.id:
                    continue
                name = getattr(btn, "base_name", None) or str(btn.label)
                entries.append(SearchEntry(
                    display=f"{short} › {name}",
                    match_text=f"{name} {short}",
                    section_id=sec_id,
                    anchor_id=None,
                    widget_id=btn.id,
                    kind="field",
                ))
        except Exception:
            pass

    # 4 — Named text field entries (from _FIELD_LABELS)
    for widget_id, (sec_id, anchor_id, human_name) in _FIELD_LABELS.items():
        short = _SECTION_SHORT.get(sec_id, sec_id)
        subsec = _SUBSECTION_LABEL.get((sec_id, anchor_id), "") if anchor_id else ""
        if subsec:
            display = f"{short} › {subsec} › {human_name}"
        else:
            display = f"{short} › {human_name}"
        entries.append(SearchEntry(
            display=display,
            match_text=f"{human_name} {short}",
            section_id=sec_id,
            anchor_id=anchor_id,
            widget_id=widget_id,
            kind="field",
        ))

    # 5 — Content entries (non-empty TextArea / Input values)
    for widget_id, (sec_id, anchor_id, human_name) in _FIELD_LABELS.items():
        section = av.sections.get(sec_id)
        if section is None:
            continue
        short = _SECTION_SHORT.get(sec_id, sec_id)
        try:
            widget = section.query_one(f"#{widget_id}")
        except Exception:
            continue
        if isinstance(widget, TextArea):
            text = widget.text
        elif isinstance(widget, TInput):
            text = widget.value
        else:
            continue
        if not text.strip():
            continue
        snip = _snippet(text)
        entries.append(SearchEntry(
            display=f"{short} › {human_name}: '{snip}'",
            match_text=text,
            section_id=sec_id,
            anchor_id=anchor_id,
            widget_id=widget_id,
            kind="content",
        ))

    # 5b — CAL-CP diagnosis workups (dynamic: one entry per pain-site
    # workup, pointing at whatever's currently actionable — the intro-form
    # Start button before it's begun, or the current trunk question after.
    # Widget ids are namespaced "<base>__<workup_id>" since Textual keeps
    # every workup's tab content mounted simultaneously — see
    # sections/diagnosis.py. A finished workup has no actionable widget
    # left (just a static result banner), so it's skipped here.
    dx_section = av.sections.get("06_diagnosis")
    if dx_section is not None:
        short = _SECTION_SHORT.get("06_diagnosis", "06_diagnosis")
        try:
            for wid, w in getattr(dx_section, "_workups", {}).items():
                if w.finished:
                    continue
                if not w.intro_done:
                    widget_id, human = f"dx_intro_start__{wid}", "Start intro form"
                else:
                    widget_id, human = f"dx_node_box__{wid}", "Current question"
                entries.append(SearchEntry(
                    display=f"{short} › {w.label} › {human}",
                    match_text=f"{w.label} {human} diagnosis CAL-CP ICD-11 chronic pain",
                    section_id="06_diagnosis",
                    anchor_id=None,
                    widget_id=widget_id,
                    kind="field",
                ))
        except Exception:
            pass

    # 6 — Objective KB special test fields
    for widget_id, region, sec_id, human_name, extra in _OBJ_KB_FIELDS:
        short = _SECTION_SHORT.get(sec_id, "Obj:Special")
        entries.append(SearchEntry(
            display=f"{short} › {region.title()} › {human_name}",
            match_text=f"{human_name} {extra} {region}",
            section_id=sec_id,
            anchor_id=None,
            widget_id=widget_id,
            kind="field",
        ))

    return entries


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def filter_entries(
    query: str,
    index: list[SearchEntry],
    max_results: int = 10,
) -> list[SearchEntry]:
    """Return up to max_results best-scoring entries for query."""
    if not query.strip():
        return []
    scored: list[tuple[int, int, SearchEntry]] = []
    for i, entry in enumerate(index):
        score = fuzzy_score(query, entry.match_text)
        if score > 0:
            scored.append((score, -i, entry))
    scored.sort(reverse=True)
    return [e for _, _, e in scored[:max_results]]
