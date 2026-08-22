"""Subjective Examination — GTK4 port of pab_assessment/sections/subjective.py.

Static field ids/keys are 1:1 with the TUI section. Dynamic body-chart note
slots reuse pab_assessment.mapping.build_prefill() unchanged. The Sleep
subsection is rendered by YamlSubsectionGtk from the *same* YAML file the TUI
uses (sections/yaml/subj_sleep_pilot.yaml) — no re-declaration.

Scope note (see plan): refresh_from_chart's live file-watcher re-sync is out
of scope for this trial — note slots are built once at load() time from
whatever _session.json currently contains.
"""

from __future__ import annotations
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..storage_bridge import pab_path_bootstrap, load_session_json  # noqa: F401
from pab_assessment.mapping import build_prefill  # noqa: E402

from ..widgets import (
    CheckButton, FlagButton, AutoTextView, TouchEntry,
    field_left_slot, make_subsection_header as _header,
)
from .yaml_subsection import YamlSubsectionGtk

_SLEEP_YAML = (
    Path(__file__).resolve().parents[3] / "assessment" / "pab_assessment" / "sections" / "yaml" / "subj_sleep_pilot.yaml"
)

_FULL_SLOTS = 3
_OVERFLOW_SLOTS = 2


def _field_row(label_text: str, widget: Gtk.Widget) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    lbl = Gtk.Label(label=label_text)
    lbl.add_css_class("field-label")
    lbl.set_halign(Gtk.Align.START)
    lbl.set_valign(Gtk.Align.START)
    lbl.set_wrap(True)
    field_left_slot(lbl)
    row.append(lbl)
    row.append(widget)
    return row


class _NoteSlot(Gtk.Box):
    """One dynamic per-note slot. full=True renders loc/nat/agg/ease; else loc/nat only."""

    def __init__(self, index: int, full: bool) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.index = index
        self.full = full
        self.stable_id: int | None = None
        self.add_css_class("note-slot")

        self.header_label = Gtk.Label(label="")
        if full:
            self.header_label.add_css_class("subsection-header")
            self.header_label.set_halign(Gtk.Align.FILL)
            self.header_label.set_hexpand(True)
            self.header_label.set_xalign(0.0)
        else:
            self.header_label.add_css_class("reference-note")
            self.header_label.set_halign(Gtk.Align.START)
        self.append(self.header_label)

        self.loc = AutoTextView(f"note_{index}_loc", min_lines=2)
        self.append(_field_row("Location & distribution:", self.loc))
        self.nat = AutoTextView(f"note_{index}_nat", min_lines=2)
        self.append(_field_row("Nature of symptoms:" if full else "Nature:", self.nat))

        if full:
            self.agg = AutoTextView(f"note_{index}_agg", min_lines=2)
            self.append(_field_row("Aggravating factors:", self.agg))
            self.ease = AutoTextView(f"note_{index}_ease", min_lines=2)
            self.append(_field_row("Easing factors:", self.ease))
        else:
            self.agg = None
            self.ease = None

    def text_widgets(self):
        yield "loc", self.loc
        yield "nat", self.nat
        if self.full:
            yield "agg", self.agg
            yield "ease", self.ease


class SubjectiveSection(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self._loading = False
        self._on_changed = None
        self.session_file = ""
        self._slot_to_stable_id: dict[int, int] = {}
        # Anchor key -> widget to focus, for Alt+letter subsection jumps
        # (mirrors main.py's action_sub_* -> BaseSection._jump_to anchors).
        self._jump_targets: dict[str, Gtk.Widget] = {}

        title = Gtk.Label(label="Subjective Examination")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        # -- Body Chart Symptoms (dynamic) ---------------------------------
        self.append(_header("Body Chart Symptoms"))
        self.body_chart_completed = CheckButton("Body chart completed", "body_chart_completed")
        self.append(self.body_chart_completed)
        self._jump_targets["symptoms"] = self.body_chart_completed

        self._note_slots: list[_NoteSlot] = []
        for i in range(_FULL_SLOTS):
            slot = _NoteSlot(i, full=True)
            slot.set_visible(False)
            self._note_slots.append(slot)
            self.append(slot)
        for i in range(_FULL_SLOTS, _FULL_SLOTS + _OVERFLOW_SLOTS):
            slot = _NoteSlot(i, full=False)
            slot.set_visible(False)
            self._note_slots.append(slot)
            self.append(slot)

        self.misc_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        misc_hdr = Gtk.Label(label="Misc symptoms (body chart — no note placed)")
        misc_hdr.add_css_class("reference-note")
        misc_hdr.set_halign(Gtk.Align.START)
        self.misc_slot.append(misc_hdr)
        self.misc_loc = AutoTextView("misc_loc", min_lines=2)
        self.misc_slot.append(_field_row("Location & distribution:", self.misc_loc))
        self.misc_nat = AutoTextView("misc_nat", min_lines=2)
        self.misc_slot.append(_field_row("Nature:", self.misc_nat))
        self.misc_slot.set_visible(False)
        self.append(self.misc_slot)

        self.no_notes_msg = Gtk.Label(label="(No body chart notes placed)")
        self.no_notes_msg.add_css_class("reference-note")
        self.no_notes_msg.set_halign(Gtk.Align.START)
        self.append(self.no_notes_msg)

        # -- History --------------------------------------------------------
        self.append(_header("History"))
        self.onset = AutoTextView("onset", min_lines=2)
        self.append(_field_row("Onset (mechanism / date):", self.onset))
        self._jump_targets["history"] = self.onset.textview
        self.duration = AutoTextView("duration", min_lines=1)
        self.append(_field_row("Duration:", self.duration))

        self.append(Gtk.Label(label="Course:", halign=Gtk.Align.START))
        course_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, homogeneous=True)
        self.course_improving = CheckButton("Improving", "course_improving")
        self.course_worsening = FlagButton("Worsening", "course_worsening")
        self.course_stable = CheckButton("Stable", "course_stable")
        self.course_fluctuating = CheckButton("Fluctuating", "course_fluctuating")
        for w in (self.course_improving, self.course_worsening, self.course_stable, self.course_fluctuating):
            course_row.append(w)
        self.append(course_row)

        self.context_at_onset = AutoTextView("context_at_onset", min_lines=2)
        self.append(_field_row("Context at onset (stress / life events):", self.context_at_onset))
        self.previous_episodes = AutoTextView("previous_episodes", min_lines=2)
        self.append(_field_row("Previous similar episodes:", self.previous_episodes))
        self.previous_treatment = AutoTextView("previous_treatment", min_lines=2)
        self.append(_field_row("Previous treatment & response:", self.previous_treatment))

        # -- Behaviour --------------------------------------------------------
        self.append(_header("Behaviour"))
        self.behaviour_boom_bust = FlagButton("Boom-Bust", "behaviour_boom_bust")
        self.behaviour_boom_bust_text = AutoTextView("behaviour_boom_bust_text", min_lines=1)
        self.append(_field_row_pair(self.behaviour_boom_bust, self.behaviour_boom_bust_text))
        self._jump_targets["behaviour"] = self.behaviour_boom_bust
        self.behaviour_avoidance = FlagButton("Avoidance", "behaviour_avoidance")
        self.behaviour_avoidance_text = AutoTextView("behaviour_avoidance_text", min_lines=1)
        self.append(_field_row_pair(self.behaviour_avoidance, self.behaviour_avoidance_text))
        self.behaviour_endurance = FlagButton("Endurance", "behaviour_endurance")
        self.behaviour_endurance_text = AutoTextView("behaviour_endurance_text", min_lines=1)
        self.append(_field_row_pair(self.behaviour_endurance, self.behaviour_endurance_text))
        self.behaviour_flareups = FlagButton("Flare-ups", "behaviour_flareups")
        self.behaviour_flareups_text = AutoTextView("behaviour_flareups_text", min_lines=1)
        self.append(_field_row_pair(self.behaviour_flareups, self.behaviour_flareups_text))
        ref = Gtk.Label(label="Predictability; duration; recovery")
        ref.add_css_class("reference-note")
        ref.set_halign(Gtk.Align.START)
        self.append(ref)

        # -- Self-Management ----------------------------------------------
        self.append(_header("Self-Management & Control"))
        self.pain_control_score = TouchEntry("pain_control_score", placeholder="0-10")
        self.append(_field_row("Perceived control over pain (0-10):", self.pain_control_score))
        self._jump_targets["management"] = self.pain_control_score
        self.flareup_prevention = AutoTextView("flareup_prevention", min_lines=2)
        self.append(_field_row("Ability to prevent flare-ups:", self.flareup_prevention))
        self.management_strategies = AutoTextView("management_strategies", min_lines=2)
        self.append(_field_row("Management strategies used:", self.management_strategies))
        self.confidence_score = TouchEntry("confidence_score", placeholder="0-10")
        self.append(_field_row("Confidence managing condition (0-10):", self.confidence_score))

        # -- Activity & Exercise --------------------------------------------
        self.append(_header("Activity & Exercise"))
        self.pre_activity_level = AutoTextView("pre_activity_level", min_lines=1)
        self.append(_field_row("Pre-injury activity level:", self.pre_activity_level))
        self._jump_targets["activity"] = self.pre_activity_level.textview
        self.current_activity_level = AutoTextView("current_activity_level", min_lines=1)
        self.append(_field_row("Current activity level:", self.current_activity_level))
        self.exercise_type = AutoTextView("exercise_type", min_lines=1)
        self.append(_field_row("Exercise type:", self.exercise_type))
        self.exercise_dose = AutoTextView("exercise_dose", min_lines=1)
        self.append(_field_row("Exercise dose (frequency / duration):", self.exercise_dose))
        self.exercise_response = AutoTextView("exercise_response", min_lines=1)
        self.append(_field_row("Response to exercise:", self.exercise_response))

        # -- Work -------------------------------------------------------------
        self.append(_header("Work"))
        self.pre_injury_role = AutoTextView("pre_injury_role", min_lines=1)
        self.append(_field_row("Pre-injury role:", self.pre_injury_role))
        self._jump_targets["work"] = self.pre_injury_role.textview
        self.pre_injury_hours = TouchEntry("pre_injury_hours", placeholder="hours")
        self.append(_field_row("Pre-injury hours per week:", self.pre_injury_hours))
        self.pre_injury_duties = AutoTextView("pre_injury_duties", min_lines=1)
        self.append(_field_row("Pre-injury duties:", self.pre_injury_duties))
        self.current_work_status = AutoTextView("current_work_status", min_lines=1)
        self.append(_field_row("Current work status:", self.current_work_status))
        self.current_hours = TouchEntry("current_hours", placeholder="hours")
        self.append(_field_row("Current hours per week:", self.current_hours))
        self.current_duties = AutoTextView("current_duties", min_lines=1)
        self.append(_field_row("Current duties & restrictions:", self.current_duties))

        # -- Sleep — YAML-driven, shared with the TUI --------------------------
        self.sleep_subsection = YamlSubsectionGtk.from_yaml(_SLEEP_YAML)
        self.append(self.sleep_subsection)
        first_sleep_widget = next(iter(self.sleep_subsection._widgets.values()), None)
        if first_sleep_widget is not None:
            self._jump_targets["sleep"] = first_sleep_widget

        # -- 24Hr Pattern -------------------------------------------------------
        self.append(_header("24Hr Pattern"))
        self.hr24_am = AutoTextView("hr24_am", min_lines=1)
        self.append(_field_row("AM:", self.hr24_am))
        self._jump_targets["24hr"] = self.hr24_am.textview
        self.hr24_day = AutoTextView("hr24_day", min_lines=1)
        self.append(_field_row("During day:", self.hr24_day))
        self.hr24_pm = AutoTextView("hr24_pm", min_lines=1)
        self.append(_field_row("PM:", self.hr24_pm))
        self.hr24_nocte = AutoTextView("hr24_nocte", min_lines=1)
        self.append(_field_row("Nocte:", self.hr24_nocte))
        self.energy_levels = AutoTextView("energy_levels", min_lines=1)
        self.append(_field_row("Energy levels by end of day:", self.energy_levels))
        self.daily_pattern_comments = AutoTextView("daily_pattern_comments", min_lines=2)
        self.append(_field_row("Daily pattern comments:", self.daily_pattern_comments))

        # -- Psychosocial -------------------------------------------------------
        self.append(_header("Psychosocial"))
        self.mood_influences = FlagButton("Mood influences pain", "mood_influences")
        self.mood_text = AutoTextView("mood_text", min_lines=1)
        self.append(_field_row_pair(self.mood_influences, self.mood_text))
        self._jump_targets["psychosocial"] = self.mood_influences
        self.social_situation = AutoTextView("social_situation", min_lines=2)
        self.append(_field_row("Social situation (home / family):", self.social_situation))
        self.financial_status = AutoTextView("financial_status", min_lines=1)
        self.append(_field_row("Financial & residential stability:", self.financial_status))
        self.cultural_considerations = AutoTextView("cultural_considerations", min_lines=1)
        self.append(_field_row("Cultural / language / religious:", self.cultural_considerations))
        self.psychological_distress = AutoTextView("psychological_distress", min_lines=2)
        self.append(_field_row("Psychological distress observed / volunteered:", self.psychological_distress))
        self.screening_tool = AutoTextView("screening_tool", min_lines=1)
        self.append(_field_row("Formal screening tool used:", self.screening_tool))

        # -- SMART Goals ----------------------------------------------------------
        self.append(_header("SMART Goals"))
        note2 = Gtk.Label(label="Potentially meaningful goals confirmed with patient:")
        note2.add_css_class("reference-note")
        note2.set_halign(Gtk.Align.START)
        self.append(note2)
        self.goals: list[AutoTextView] = []
        for i in range(1, 5):
            ta = AutoTextView(f"goal_{i}", min_lines=1)
            self.append(_field_row(f"{i}.", ta))
            self.goals.append(ta)
        self._jump_targets["goals"] = self.goals[0].textview

        # -- Suicide / Self-Harm Risk ----------------------------------------------
        self.append(_header("Suicide / Self-Harm Risk"))
        self.self_harm_risk = FlagButton("Thoughts of self-harm or suicide", "self_harm_risk")
        self.append(self.self_harm_risk)
        self._jump_targets["risk"] = self.self_harm_risk
        self.harm_plan = AutoTextView("harm_plan", min_lines=1)
        self.append(_field_row("Plan (if yes):", self.harm_plan))
        self.harm_means = AutoTextView("harm_means", min_lines=1)
        self.append(_field_row("Means (if yes):", self.harm_means))
        self.harm_intent = AutoTextView("harm_intent", min_lines=1)
        self.append(_field_row("Intent (if yes):", self.harm_intent))
        self.harm_action = AutoTextView("harm_action", min_lines=1)
        self.append(_field_row("Action taken (if yes):", self.harm_action))

        self._wire_change_events()

    # ------------------------------------------------------------------

    _TOGGLE_ATTRS = [
        "body_chart_completed",
        "course_improving", "course_worsening", "course_stable", "course_fluctuating",
        "behaviour_boom_bust", "behaviour_avoidance", "behaviour_endurance", "behaviour_flareups",
        "mood_influences", "self_harm_risk",
    ]
    _TEXT_ATTRS = [
        "onset", "duration", "context_at_onset", "previous_episodes", "previous_treatment",
        "behaviour_boom_bust_text", "behaviour_avoidance_text",
        "behaviour_endurance_text", "behaviour_flareups_text",
        "flareup_prevention", "management_strategies",
        "pre_activity_level", "current_activity_level",
        "exercise_type", "exercise_dose", "exercise_response",
        "pre_injury_role", "pre_injury_duties",
        "current_work_status", "current_duties",
        "hr24_am", "hr24_day", "hr24_pm", "hr24_nocte",
        "energy_levels", "daily_pattern_comments",
        "mood_text",
        "social_situation", "financial_status", "cultural_considerations",
        "psychological_distress", "screening_tool",
        "harm_plan", "harm_means", "harm_intent", "harm_action",
        "goal_1", "goal_2", "goal_3", "goal_4",
    ]
    _INPUT_ATTRS = ["pain_control_score", "confidence_score", "pre_injury_hours", "current_hours"]

    def _wire_change_events(self) -> None:
        for attr in self._TOGGLE_ATTRS:
            getattr(self, attr).connect("changed", self._field_changed)
        for i, ta in enumerate(self.goals, start=1):
            ta.textview.get_buffer().connect("changed", self._field_changed)
        for attr in self._TEXT_ATTRS:
            if attr.startswith("goal_"):
                continue
            getattr(self, attr).textview.get_buffer().connect("changed", self._field_changed)
        for attr in self._INPUT_ATTRS:
            getattr(self, attr).connect("changed", self._field_changed)
        self.sleep_subsection.connect("changed", self._field_changed)
        for slot in self._note_slots:
            for _, w in slot.text_widgets():
                w.textview.get_buffer().connect("changed", self._field_changed)
        self.misc_loc.textview.get_buffer().connect("changed", self._field_changed)
        self.misc_nat.textview.get_buffer().connect("changed", self._field_changed)

    def _field_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._on_changed:
            self._on_changed()

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    # ------------------------------------------------------------------
    # Dynamic note slots — reuses pab_assessment.mapping.build_prefill unchanged
    # ------------------------------------------------------------------

    def _rebuild_note_slots(self, saved_note_fields: dict, prefill: dict) -> None:
        for slot in self._note_slots:
            slot.set_visible(False)
        self.misc_slot.set_visible(False)
        self._slot_to_stable_id.clear()

        notes = prefill.get("notes", [])
        total_slots = len(self._note_slots)

        for i, note in enumerate(notes[:total_slots]):
            slot = self._note_slots[i]
            sid = note["stable_id"]
            num = note["number"]
            saved = saved_note_fields.get(str(sid), {})
            self._slot_to_stable_id[i] = sid
            slot.set_visible(True)

            region = note["location_distribution"] or f"Note {num}"
            loc = saved.get("loc") or note["location_distribution"] or ""
            nat = saved.get("nat") or note["nature"] or ""

            if slot.full:
                slot.header_label.set_label(f"Note {num} — {region}")
                slot.agg.text = saved.get("agg", "")
                slot.ease.text = saved.get("ease", "")
            else:
                slot.header_label.set_label(f"Misc symptoms ({num})")

            slot.loc.text = loc
            slot.nat.text = nat

        misc = prefill.get("misc", {})
        misc_loc = saved_note_fields.get("misc_loc") or misc.get("location_distribution", "")
        misc_nat = saved_note_fields.get("misc_nat") or misc.get("nature", "")
        if misc_loc or misc_nat:
            self.misc_slot.set_visible(True)
            self.misc_loc.text = misc_loc
            self.misc_nat.text = misc_nat

        has_content = bool(notes) or bool(misc_loc or misc_nat)
        self.no_notes_msg.set_visible(not has_content)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def collect(self) -> dict:
        data = {}
        for attr in self._TOGGLE_ATTRS:
            data[attr] = getattr(self, attr).value

        note_fields: dict[str, dict] = {}
        for i, sid in self._slot_to_stable_id.items():
            slot = self._note_slots[i]
            if not slot.get_visible():
                continue
            note_fields[str(sid)] = {
                "loc": slot.loc.text,
                "nat": slot.nat.text,
                "agg": slot.agg.text if slot.full else "",
                "ease": slot.ease.text if slot.full else "",
            }
        data["note_fields"] = note_fields

        misc_visible = self.misc_slot.get_visible()
        data["misc_loc"] = self.misc_loc.text if misc_visible else ""
        data["misc_nat"] = self.misc_nat.text if misc_visible else ""

        for attr in self._TEXT_ATTRS:
            if attr.startswith("goal_"):
                idx = int(attr.split("_")[1]) - 1
                data[attr] = self.goals[idx].text
            else:
                data[attr] = getattr(self, attr).text

        for attr in self._INPUT_ATTRS:
            data[attr] = getattr(self, attr).text

        data.update(self.sleep_subsection.collect())
        return data

    def load(self, data: dict) -> None:
        self._loading = True
        try:
            subjective = data if isinstance(data, dict) else {}

            prefill: dict = {}
            if self.session_file:
                session_json = load_session_json(self.session_file)
                if session_json:
                    try:
                        prefill = build_prefill(session_json)
                    except Exception:
                        prefill = {}

            self._rebuild_note_slots(subjective.get("note_fields", {}), prefill)

            for attr in self._TOGGLE_ATTRS:
                getattr(self, attr).set_value(subjective.get(attr))

            for attr in self._TEXT_ATTRS:
                if attr.startswith("goal_"):
                    idx = int(attr.split("_")[1]) - 1
                    self.goals[idx].text = subjective.get(attr, "")
                else:
                    getattr(self, attr).text = subjective.get(attr, "")

            for attr in self._INPUT_ATTRS:
                getattr(self, attr).text = subjective.get(attr, "")

            self.sleep_subsection.load(subjective)
        finally:
            self._loading = False

    def is_complete(self) -> bool:
        return self.self_harm_risk.value is not None

    def focus_first_field(self) -> None:
        self.body_chart_completed.grab_focus()

    def jump_to(self, anchor: str) -> None:
        """Alt+letter subsection jump — mirrors main.py's action_sub_* bindings."""
        target = self._jump_targets.get(anchor)
        if target is not None:
            target.grab_focus()


def _field_row_pair(flag_widget: Gtk.Widget, text_widget: Gtk.Widget) -> Gtk.Box:
    """A toggle button standing in for the row's label, paired with a field.

    field_left_slot() forces the toggle to the exact same width as every
    plain label (FIELD_LEFT_COLUMN_PX) so its row's text field starts at the
    same x position as every other field row — this is the single place that
    rule is enforced, so it can never drift out of sync section by section.
    """
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    field_left_slot(flag_widget)
    row.append(flag_widget)
    row.append(text_widget)
    return row
