"""Catalog content synchronization for non-clinical test explanations.

Provides an idempotent, safe mechanism to update active LabTest descriptions
to neutral, customer-service language without schema migrations or catalog drops.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models.test import LabTest

logger = logging.getLogger("medilab.catalog_sync")

# Authoritative non-clinical, customer-service explanations for all active tests
AUDITED_TEST_DESCRIPTIONS: dict[str, str] = {
    "CBC": (
        "Measures red blood cells, white blood cells, platelets, and hemoglobin "
        "to assess general blood health and counts."
    ),
    "FERRITIN": (
        "Measures ferritin levels in the blood, an indicator of the body's stored iron reserves."
    ),
    "LIPID": (
        "Measures total cholesterol, HDL, LDL, and triglycerides to evaluate "
        "lipid concentrations in the bloodstream."
    ),
    "LFT": (
        "Measures liver enzymes and proteins including ALT, AST, alkaline phosphatase, "
        "and bilirubin to assess hepatic panel values."
    ),
    "KFT": (
        "Measures kidney function markers including creatinine, blood urea nitrogen, and uric acid."
    ),
    "TSH": (
        "TSH is a blood test that measures thyroid-stimulating hormone, "
        "which is involved in regulating thyroid function."
    ),
    "VITD": ("Measures circulating 25-hydroxy vitamin D levels in the blood."),
    "HBA1C": ("Measures average blood glucose concentration over the preceding 2 to 3 months."),
    "FBS": ("Determines blood glucose level following an overnight 8-hour fast."),
    "URINE": (
        "Microscopic and chemical examination of urine evaluating physical characteristics, "
        "cellular components, and chemical markers."
    ),
}


def sync_catalog_descriptions(session: Any = None) -> int:
    """Safely update active LabTest descriptions to audited non-clinical language.

    Returns the count of updated tests. Idempotent and scoped strictly to known codes.
    """
    s = session or db.session
    updated_count = 0

    for code, clean_desc in AUDITED_TEST_DESCRIPTIONS.items():
        test = s.execute(select(LabTest).where(LabTest.code == code)).scalar_one_or_none()
        if test is not None and test.short_description != clean_desc:
            test.short_description = clean_desc
            updated_count += 1
            logger.info("Updated LabTest %s description to audited non-clinical text.", code)

    if updated_count > 0:
        s.flush()

    return updated_count
