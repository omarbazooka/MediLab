"""Unit tests verifying test catalog descriptions are non-clinical, complete, and audited."""

from __future__ import annotations

import re

from app.services.catalog_sync import AUDITED_TEST_DESCRIPTIONS

PROHIBITED_DIAGNOSTIC_PATTERNS = [
    r"(?i)\bdiagnos(?:e|es|is|ing)\b",
    r"(?i)\bdetects?\s+(?:that\s+)?you\s+have\b",
    r"(?i)\byou\s+need\s+this\s+if\b",
    r"(?i)\bproves?\s+(?:that\s+)?you\b",
    r"(?i)\bprescribe[sd]?\b",
    r"(?i)\bto\s+detect\s+anemia\b",
    r"(?i)\bevaluate\s+cardiovascular\s+risk\b",
    r"(?i)\bscreen\s+for\s+infections\b",
]

EXPECTED_ACTIVE_CODES = {
    "CBC",
    "FERRITIN",
    "LIPID",
    "LFT",
    "KFT",
    "TSH",
    "VITD",
    "HBA1C",
    "FBS",
    "URINE",
}


def test_all_expected_active_codes_audited() -> None:
    """Ensure all 10 active diagnostic tests have audited descriptions."""
    for code in EXPECTED_ACTIVE_CODES:
        assert code in AUDITED_TEST_DESCRIPTIONS
        desc = AUDITED_TEST_DESCRIPTIONS[code].strip()
        assert len(desc) > 20, f"Description for {code} is too short."


def test_no_prohibited_clinical_patterns_in_audited_descriptions() -> None:
    """Verify that none of the audited descriptions contain diagnostic/prescriptive language."""
    for code, desc in AUDITED_TEST_DESCRIPTIONS.items():
        for pat in PROHIBITED_DIAGNOSTIC_PATTERNS:
            match = re.search(pat, desc)
            assert match is None, (
                f"Test {code} description contains prohibited clinical pattern '{pat}': {desc}"
            )


def test_tsh_canonical_customer_service_wording() -> None:
    """TSH description strictly follows approved neutral definition."""
    tsh_desc = AUDITED_TEST_DESCRIPTIONS["TSH"]
    assert "thyroid-stimulating hormone" in tsh_desc
    assert "regulating thyroid function" in tsh_desc
    assert "screens for thyroid gland disorders" not in tsh_desc.lower()
