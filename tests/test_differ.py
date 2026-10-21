"""Unit tests for the section differ engine."""

from app.models.graph import ChangeType
from app.services.differ import LabelDiffer, compute_sha256


def test_diff_section_added():
    differ = LabelDiffer()
    new_text = "WARNING: Risk of hepatotoxicity in patients with underlying liver disease."
    result = differ.diff_section("boxed_warning", text_old=None, text_new=new_text)

    assert result.change_type == ChangeType.ADDED
    assert result.section_name == "boxed_warning"
    assert result.added_lines == 1
    assert result.removed_lines == 0
    assert result.similarity_ratio == 0.0
    assert "newly added" in result.summary
    assert "+WARNING:" in result.diff_text


def test_diff_section_removed():
    differ = LabelDiffer()
    old_text = "Contraindicated in severe renal impairment."
    result = differ.diff_section("contraindications", text_old=old_text, text_new=None)

    assert result.change_type == ChangeType.REMOVED
    assert result.section_name == "contraindications"
    assert result.added_lines == 0
    assert result.removed_lines == 1
    assert result.similarity_ratio == 0.0
    assert "was removed" in result.summary
    assert "-Contraindicated" in result.diff_text


def test_diff_section_unchanged():
    differ = LabelDiffer()
    text = "Dosage is 10 mg to 80 mg once daily."
    result = differ.diff_section("dosage_and_administration", text_old=text, text_new=text)

    assert result.change_type == ChangeType.UNCHANGED
    assert result.similarity_ratio == 1.0
    assert result.diff_text == ""
    assert result.added_lines == 0
    assert result.removed_lines == 0


def test_diff_section_modified():
    differ = LabelDiffer()
    old_text = "Myopathy: Rare cases of rhabdomyolysis reported."
    new_text = "Myopathy and Rhabdomyolysis: Discontinue if markedly elevated CK occurs.\nImmune-mediated necrotizing myopathy (IMNM) reported."

    result = differ.diff_section(
        "warnings_and_precautions",
        text_old=old_text,
        text_new=new_text,
        from_version="v1",
        to_version="v2",
    )

    assert result.change_type == ChangeType.MODIFIED
    assert result.added_lines >= 1
    assert result.removed_lines >= 1
    assert 0.0 < result.similarity_ratio < 1.0
    assert "v1/warnings_and_precautions" in result.diff_text
    assert "v2/warnings_and_precautions" in result.diff_text


def test_diff_label_versions_multi_section():
    differ = LabelDiffer()
    v1_sections = {
        "contraindications": "Active liver disease.",
        "indications_and_usage": "Indicated for hypercholesterolemia.",
    }
    v2_sections = {
        "boxed_warning": "WARNING: IMNM risk.",
        "contraindications": "Active liver disease.\nHypersensitivity to atorvastatin.",
        "indications_and_usage": "Indicated for hypercholesterolemia.",
    }

    diffs = differ.diff_label_versions(
        old_sections=v1_sections,
        new_sections=v2_sections,
        from_version="1",
        to_version="2",
        include_unchanged=False,
    )

    diff_map = {d.section_name: d for d in diffs}

    assert "boxed_warning" in diff_map
    assert diff_map["boxed_warning"].change_type == ChangeType.ADDED

    assert "contraindications" in diff_map
    assert diff_map["contraindications"].change_type == ChangeType.MODIFIED

    # indications_and_usage is unchanged so not included
    assert "indications_and_usage" not in diff_map


def test_compute_sha256():
    h1 = compute_sha256("test string")
    h2 = compute_sha256("test string")
    h3 = compute_sha256("different string")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64

