"""Tests for accessibility._looks_like_continue and _is_button."""

import pytest
from claude_auto_continue.accessibility import (
    CONTINUE_LABELS,
    _is_button,
    _looks_like_continue,
)


# --- _looks_like_continue: exact matches ------------------------------------

class TestExactLabels:
    @pytest.mark.parametrize("label", CONTINUE_LABELS)
    def test_all_builtin_labels_match(self, label):
        assert _looks_like_continue(label)

    @pytest.mark.parametrize("label", CONTINUE_LABELS)
    def test_case_insensitive(self, label):
        assert _looks_like_continue(label.upper())
        assert _looks_like_continue(label.title())

    @pytest.mark.parametrize("label", CONTINUE_LABELS)
    def test_whitespace_stripped(self, label):
        assert _looks_like_continue(f"  {label}  ")


# --- _looks_like_continue: prefix matching ----------------------------------

class TestPrefixMatching:
    @pytest.mark.parametrize("label", [
        "Continue with tools",
        "Continue this conversation",
        "Continue where we left off",
        "Resume the session",
        "Resume after pause",
        "Proceed with generation",
        "Keep going with the task",
    ])
    def test_valid_prefixes_match(self, label):
        assert _looks_like_continue(label)

    def test_prefix_length_cap(self):
        assert _looks_like_continue("Continue " + "x" * 40)
        assert not _looks_like_continue("Continue " + "x" * 50)

    @pytest.mark.parametrize("label", [
        "Continue?",
        "Continue!",
        "Continue...",
        "Resume - ready",
        "Proceed: next step",
        "Continue, please",
    ])
    def test_punctuation_after_prefix(self, label):
        assert _looks_like_continue(label)

    @pytest.mark.parametrize("label", [
        "continue",
        "Continue",
        "CONTINUE",
        "resume",
        "Resume",
        "proceed",
        "Proceed",
        "keep going",
        "Keep Going",
    ])
    def test_bare_prefixes(self, label):
        assert _looks_like_continue(label)


# --- _looks_like_continue: false positives that must NOT match ---------------

class TestFalsePositives:
    @pytest.mark.parametrize("label", [
        "Retry",
        "Try again",
        "Retry generation",
        "Cancel",
        "Stop",
        "OK",
        "Submit",
        "Send",
        "Copy",
        "Edit",
        "Delete",
        "Close",
        "New chat",
        "",
        "   ",
        # File names starting with "resume" or "continue" — must NOT match
        "RESUME_MAIN_NEW.zip",
        "resume_v2.pdf",
        "continued_fraction.py",
        "proceedings.docx",
        "ContinueButton.tsx",
        "resume2024.doc",
    ])
    def test_non_continue_labels_rejected(self, label):
        assert not _looks_like_continue(label)


# --- _looks_like_continue: extra_labels parameter ---------------------------

class TestExtraLabels:
    def test_custom_label_matches(self):
        assert not _looks_like_continue("go ahead")
        assert _looks_like_continue("go ahead", extra_labels=("go ahead",))

    def test_builtin_still_works_with_extras(self):
        assert _looks_like_continue("continue", extra_labels=("go ahead",))


# --- _is_button -------------------------------------------------------------

class TestIsButton:
    @pytest.mark.parametrize("role", [
        "AXButton",
        "AXMenuItem",
        "AXRadioButton",
        "AXPopUpButton",
        "AXToggleButton",
    ])
    def test_button_roles(self, role):
        assert _is_button(role)

    @pytest.mark.parametrize("role", [
        "AXStaticText",
        "AXGroup",
        "AXImage",
        "AXWebArea",
        "",
    ])
    def test_non_button_roles(self, role):
        assert not _is_button(role)
