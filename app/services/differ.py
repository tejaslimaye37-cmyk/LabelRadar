"""Section-by-section diffing engine for drug label revisions."""

import difflib
import hashlib

from pydantic import BaseModel

from app.models.graph import ChangeType


class SectionDiffResult(BaseModel):
    """Result of diffing a single section between two label versions."""

    section_name: str
    change_type: ChangeType
    diff_text: str
    added_lines: int
    removed_lines: int
    similarity_ratio: float
    old_hash: str
    new_hash: str
    summary: str


def compute_sha256(text: str) -> str:
    """Computes SHA-256 hash of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LabelDiffer:
    """Engine for generating unified diffs and metadata between drug label versions."""

    @staticmethod
    def diff_section(
        section_name: str,
        text_old: str | None,
        text_new: str | None,
        from_version: str = "v_old",
        to_version: str = "v_new",
    ) -> SectionDiffResult:
        """Diffs a single section between two versions."""
        old_normalized = (text_old or "").strip()
        new_normalized = (text_new or "").strip()

        old_hash = compute_sha256(old_normalized)
        new_hash = compute_sha256(new_normalized)

        # 1. Section Added
        if not old_normalized and new_normalized:
            new_lines = new_normalized.splitlines()
            unified_lines = list(
                difflib.unified_diff(
                    [],
                    [line + "\n" for line in new_lines],
                    fromfile=f"{from_version}/{section_name}",
                    tofile=f"{to_version}/{section_name}",
                )
            )
            return SectionDiffResult(
                section_name=section_name,
                change_type=ChangeType.ADDED,
                diff_text="".join(unified_lines),
                added_lines=len(new_lines),
                removed_lines=0,
                similarity_ratio=0.0,
                old_hash=old_hash,
                new_hash=new_hash,
                summary=f"Section '{section_name}' was newly added ({len(new_lines)} lines).",
            )

        # 2. Section Removed
        if old_normalized and not new_normalized:
            old_lines = old_normalized.splitlines()
            unified_lines = list(
                difflib.unified_diff(
                    [line + "\n" for line in old_lines],
                    [],
                    fromfile=f"{from_version}/{section_name}",
                    tofile=f"{to_version}/{section_name}",
                )
            )
            return SectionDiffResult(
                section_name=section_name,
                change_type=ChangeType.REMOVED,
                diff_text="".join(unified_lines),
                added_lines=0,
                removed_lines=len(old_lines),
                similarity_ratio=0.0,
                old_hash=old_hash,
                new_hash=new_hash,
                summary=f"Section '{section_name}' was removed ({len(old_lines)} lines deleted).",
            )

        # 3. Both Identical / Unchanged
        if old_hash == new_hash or old_normalized == new_normalized:
            return SectionDiffResult(
                section_name=section_name,
                change_type=ChangeType.UNCHANGED,
                diff_text="",
                added_lines=0,
                removed_lines=0,
                similarity_ratio=1.0,
                old_hash=old_hash,
                new_hash=new_hash,
                summary=f"Section '{section_name}' is unchanged.",
            )

        # 4. Section Modified
        old_lines = [line + "\n" for line in old_normalized.splitlines()]
        new_lines = [line + "\n" for line in new_normalized.splitlines()]

        diff_gen = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"{from_version}/{section_name}",
                tofile=f"{to_version}/{section_name}",
            )
        )
        diff_text = "".join(diff_gen)

        added = sum(1 for line in diff_gen if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff_gen if line.startswith("-") and not line.startswith("---"))
        ratio = round(difflib.SequenceMatcher(None, old_normalized, new_normalized).ratio(), 4)

        return SectionDiffResult(
            section_name=section_name,
            change_type=ChangeType.MODIFIED,
            diff_text=diff_text,
            added_lines=added,
            removed_lines=removed,
            similarity_ratio=ratio,
            old_hash=old_hash,
            new_hash=new_hash,
            summary=f"Section '{section_name}' modified: +{added}/-{removed} lines (similarity: {ratio:.1%}).",
        )

    @classmethod
    def diff_label_versions(
        cls,
        old_sections: dict[str, str],
        new_sections: dict[str, str],
        from_version: str = "v_old",
        to_version: str = "v_new",
        include_unchanged: bool = False,
    ) -> list[SectionDiffResult]:
        """Diffs all sections between two versions and returns list of SectionDiffResult."""
        all_section_keys = sorted(set(old_sections.keys()) | set(new_sections.keys()))
        diff_results: list[SectionDiffResult] = []

        for sec_name in all_section_keys:
            old_text = old_sections.get(sec_name)
            new_text = new_sections.get(sec_name)
            res = cls.diff_section(sec_name, old_text, new_text, from_version, to_version)
            if include_unchanged or res.change_type != ChangeType.UNCHANGED:
                diff_results.append(res)

        return diff_results
