"""Deterministic, idempotent seed script for MediLab AI catalog, branches, and policies.

Usage:
    uv run python scripts/seed_db.py
"""

from __future__ import annotations

import sys
from datetime import date, time
from decimal import Decimal
from pathlib import Path

# Ensure workspace root is in sys.path when executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models.branch import AvailabilitySlot, Branch
from app.models.knowledge import KnowledgeDocument
from app.models.package import Package, PackageTest
from app.models.test import LabTest, TestCategory


def seed_categories() -> dict[str, TestCategory]:
    """Seed test categories idempotently."""
    categories_data = [
        {"name": "Hematology", "slug": "hematology"},
        {"name": "Clinical Chemistry", "slug": "clinical-chemistry"},
        {"name": "Endocrinology & Hormones", "slug": "endocrinology-hormones"},
        {"name": "Diabetes Care", "slug": "diabetes-care"},
        {"name": "General Wellness", "slug": "general-wellness"},
    ]
    seeded: dict[str, TestCategory] = {}
    for data in categories_data:
        cat = db.session.execute(
            select(TestCategory).where(TestCategory.slug == data["slug"])
        ).scalar_one_or_none()
        if cat is None:
            cat = TestCategory(name=data["name"], slug=data["slug"], active=True)
            db.session.add(cat)
            db.session.flush()
        seeded[data["slug"]] = cat
    return seeded


def seed_lab_tests(categories: dict[str, TestCategory]) -> dict[str, LabTest]:
    """Seed diagnostic laboratory tests idempotently."""
    from app.services.catalog_sync import AUDITED_TEST_DESCRIPTIONS

    tests_data = [
        {
            "code": "CBC",
            "name": "Complete Blood Count (CBC)",
            "category_slug": "hematology",
            "short_description": AUDITED_TEST_DESCRIPTIONS["CBC"],
            "sample_type": "Whole Blood (EDTA)",
            "price": Decimal("250.00"),
            "result_turnaround_text": "Same Day (4 hours)",
            "active": True,
        },
        {
            "code": "FERRITIN",
            "name": "Serum Ferritin",
            "category_slug": "hematology",
            "short_description": AUDITED_TEST_DESCRIPTIONS["FERRITIN"],
            "sample_type": "Serum",
            "price": Decimal("280.00"),
            "result_turnaround_text": "24 Hours",
            "active": True,
        },
        {
            "code": "LIPID",
            "name": "Lipid Profile Panel",
            "category_slug": "clinical-chemistry",
            "short_description": AUDITED_TEST_DESCRIPTIONS["LIPID"],
            "sample_type": "Serum (10-12 hr fasting)",
            "price": Decimal("320.00"),
            "result_turnaround_text": "Same Day (4 hours)",
            "active": True,
        },
        {
            "code": "LFT",
            "name": "Liver Function Tests (LFT)",
            "category_slug": "clinical-chemistry",
            "short_description": AUDITED_TEST_DESCRIPTIONS["LFT"],
            "sample_type": "Serum",
            "price": Decimal("380.00"),
            "result_turnaround_text": "Same Day (5 hours)",
            "active": True,
        },
        {
            "code": "KFT",
            "name": "Kidney Function Tests (KFT)",
            "category_slug": "clinical-chemistry",
            "short_description": AUDITED_TEST_DESCRIPTIONS["KFT"],
            "sample_type": "Serum",
            "price": Decimal("300.00"),
            "result_turnaround_text": "Same Day (4 hours)",
            "active": True,
        },
        {
            "code": "TSH",
            "name": "Thyroid Stimulating Hormone (TSH)",
            "category_slug": "endocrinology-hormones",
            "short_description": AUDITED_TEST_DESCRIPTIONS["TSH"],
            "sample_type": "Serum",
            "price": Decimal("220.00"),
            "result_turnaround_text": "24 Hours",
            "active": True,
        },
        {
            "code": "VITD",
            "name": "Vitamin D (25-Hydroxy)",
            "category_slug": "endocrinology-hormones",
            "short_description": AUDITED_TEST_DESCRIPTIONS["VITD"],
            "sample_type": "Serum",
            "price": Decimal("650.00"),
            "result_turnaround_text": "48 Hours",
            "active": True,
        },
        {
            "code": "HBA1C",
            "name": "Glycated Hemoglobin (HbA1c)",
            "category_slug": "diabetes-care",
            "short_description": AUDITED_TEST_DESCRIPTIONS["HBA1C"],
            "sample_type": "Whole Blood (EDTA)",
            "price": Decimal("200.00"),
            "result_turnaround_text": "Same Day (3 hours)",
            "active": True,
        },
        {
            "code": "FBS",
            "name": "Fasting Blood Sugar (FBS)",
            "category_slug": "diabetes-care",
            "short_description": AUDITED_TEST_DESCRIPTIONS["FBS"],
            "sample_type": "Fluoride Plasma",
            "price": Decimal("90.00"),
            "result_turnaround_text": "2 Hours",
            "active": True,
        },
        {
            "code": "URINE",
            "name": "Routine Urine Analysis",
            "category_slug": "general-wellness",
            "short_description": AUDITED_TEST_DESCRIPTIONS["URINE"],
            "sample_type": "Clean Catch Urine",
            "price": Decimal("80.00"),
            "result_turnaround_text": "2 Hours",
            "active": True,
        },
        {
            "code": "ARCHIVED_TEST",
            "name": "Legacy Diagnostic Screen (Archived)",
            "category_slug": "general-wellness",
            "short_description": "Discontinued screening method maintained for historical audit verification.",
            "sample_type": "Serum",
            "price": Decimal("150.00"),
            "result_turnaround_text": "N/A",
            "active": False,
        },
    ]

    seeded: dict[str, LabTest] = {}
    for item in tests_data:
        test = db.session.execute(
            select(LabTest).where(LabTest.code == item["code"])
        ).scalar_one_or_none()
        category = categories[item["category_slug"]]
        if test is None:
            test = LabTest(
                code=item["code"],
                name=item["name"],
                category_id=category.id,
                short_description=item["short_description"],
                sample_type=item["sample_type"],
                price=item["price"],
                result_turnaround_text=item["result_turnaround_text"],
                active=item["active"],
            )
            db.session.add(test)
            db.session.flush()
        else:
            # Sync description if it differs from audited non-clinical explanation
            if test.short_description != item["short_description"]:
                test.short_description = item["short_description"]
                db.session.flush()
        seeded[item["code"]] = test
    return seeded


def seed_packages(tests: dict[str, LabTest]) -> dict[str, Package]:
    """Seed multi-test packages and package membership idempotently."""
    packages_data = [
        {
            "name": "Comprehensive Health Checkup",
            "description": "Thorough preventive screening package covering hematology, liver, kidneys, lipids, and glucose.",
            "price": Decimal("1050.00"),
            "active": True,
            "test_codes": ["CBC", "LIPID", "LFT", "KFT", "FBS"],
        },
        {
            "name": "Diabetes Monitoring Package",
            "description": "Essential quarterly monitoring for diabetic patients including glycemic and kidney function assessment.",
            "price": Decimal("680.00"),
            "active": True,
            "test_codes": ["HBA1C", "FBS", "KFT", "LIPID"],
        },
        {
            "name": "Vitality & Wellness Panel",
            "description": "Specialized panel assessing energy, bone metabolism, and thyroid regulation.",
            "price": Decimal("980.00"),
            "active": True,
            "test_codes": ["CBC", "TSH", "VITD", "FERRITIN"],
        },
    ]

    seeded: dict[str, Package] = {}
    for item in packages_data:
        pkg = db.session.execute(
            select(Package).where(Package.name == item["name"])
        ).scalar_one_or_none()
        if pkg is None:
            pkg = Package(
                name=item["name"],
                description=item["description"],
                price=item["price"],
                active=item["active"],
            )
            db.session.add(pkg)
            db.session.flush()

        # Ensure package membership associations exist
        for code in item["test_codes"]:
            test = tests.get(code)
            if test:
                assoc = db.session.execute(
                    select(PackageTest).where(
                        PackageTest.package_id == pkg.id,
                        PackageTest.test_id == test.id,
                    )
                ).scalar_one_or_none()
                if assoc is None:
                    db.session.add(PackageTest(package_id=pkg.id, test_id=test.id))
        db.session.flush()
        seeded[item["name"]] = pkg

    return seeded


def seed_branches() -> dict[str, Branch]:
    """Seed physical laboratory branches idempotently with standardized 09:00-19:00 hours."""
    branches_data = [
        {
            "name": "Nasr City Branch",
            "address": "14 Abbas El Akkad Street, Nasr City, Cairo",
            "phone": "+20224011234",
            "opening_hours": {
                "saturday_thursday": "09:00 - 19:00",
                "friday": "09:00 - 19:00",
            },
        },
        {
            "name": "Maadi Branch",
            "address": "25 Road 9, Maadi, Cairo",
            "phone": "+20223581234",
            "opening_hours": {
                "saturday_thursday": "09:00 - 19:00",
                "friday": "09:00 - 19:00",
            },
        },
        {
            "name": "Dokki Branch",
            "address": "12 Mossadak Street, Dokki, Giza",
            "phone": "+20233371234",
            "opening_hours": {
                "saturday_thursday": "09:00 - 19:00",
                "friday": "09:00 - 19:00",
            },
        },
        {
            "name": "New Cairo Branch",
            "address": "55 North 90th Street, 5th Settlement, New Cairo",
            "phone": "+20228121234",
            "opening_hours": {
                "saturday_thursday": "09:00 - 19:00",
                "friday": "09:00 - 19:00",
            },
        },
    ]

    seeded: dict[str, Branch] = {}
    for item in branches_data:
        branch = db.session.execute(
            select(Branch).where(Branch.name == item["name"])
        ).scalar_one_or_none()
        if branch is None:
            branch = Branch(
                name=item["name"],
                address=item["address"],
                phone=item["phone"],
                opening_hours_json=item["opening_hours"],
                active=True,
            )
            db.session.add(branch)
            db.session.flush()
        else:
            branch.opening_hours_json = item["opening_hours"]
            db.session.flush()
        seeded[item["name"]] = branch

    return seeded


def seed_availability_slots(branches: dict[str, Branch]) -> int:
    """Seed discrete 30-minute appointment availability slots (09:00-18:30) with capacity=1."""
    from datetime import timedelta

    start_date = date(2026, 9, 15)
    dates = [start_date + timedelta(days=i) for i in range(14)]
    # Discrete 30-minute slots: 09:00 to 18:30 (19:00 is closing time, not a valid start slot)
    times = [time(hour, minute) for hour in range(9, 19) for minute in (0, 30)]
    slot_count = 0

    # 1. Branch slots for each physical branch
    for branch in branches.values():
        for slot_date in dates:
            for slot_time in times:
                existing = db.session.execute(
                    select(AvailabilitySlot).where(
                        AvailabilitySlot.branch_id == branch.id,
                        AvailabilitySlot.visit_type == "BRANCH",
                        AvailabilitySlot.date == slot_date,
                        AvailabilitySlot.time == slot_time,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    db.session.add(
                        AvailabilitySlot(
                            branch_id=branch.id,
                            visit_type="BRANCH",
                            date=slot_date,
                            time=slot_time,
                            capacity=1,
                            reserved_count=0,
                            active=True,
                        )
                    )
                    slot_count += 1
                elif existing.capacity != 1:
                    existing.capacity = 1
                    db.session.flush()

    # 2. Home visit pool slots (branch_id is NULL)
    for slot_date in dates:
        for slot_time in times:
            existing_home = db.session.execute(
                select(AvailabilitySlot).where(
                    AvailabilitySlot.branch_id.is_(None),
                    AvailabilitySlot.visit_type == "HOME",
                    AvailabilitySlot.date == slot_date,
                    AvailabilitySlot.time == slot_time,
                )
            ).scalar_one_or_none()
            if existing_home is None:
                db.session.add(
                    AvailabilitySlot(
                        branch_id=None,
                        visit_type="HOME",
                        date=slot_date,
                        time=slot_time,
                        capacity=1,
                        reserved_count=0,
                        active=True,
                    )
                )
                slot_count += 1
            elif existing_home.capacity != 1:
                existing_home.capacity = 1
                db.session.flush()

    db.session.flush()
    return slot_count


def seed_knowledge_documents() -> dict[str, KnowledgeDocument]:
    """Seed authoritative non-clinical knowledge documents.

    If knowledge_manifest.json is present, bootstraps the canonical 7 MediLab PDF documents
    in PENDING status (deferring detailed chunk content to the PDF ingestion service).
    Deactivates any obsolete legacy inline documents to prevent competing sources of truth.
    """
    import json
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent
    manifest_paths = [
        base_dir / "knowledge" / "knowledge_manifest.json",
        base_dir / "knowledge_manifest.json",
    ]

    manifest_file = next((p for p in manifest_paths if p.exists()), None)

    if manifest_file:
        with open(manifest_file, encoding="utf-8") as f:
            manifest_data = json.load(f)

        docs_data = [
            {
                "title": item["title"],
                "category": item["category"],
                "content": (
                    f"Authoritative MediLab policy document from {item['source_file']}. "
                    "Full text and structure-aware chunking managed by PDF ingestion."
                ),
                "version": item.get("version", 1),
                "active": item.get("active", True),
            }
            for item in manifest_data
        ]
        manifest_titles = {d["title"] for d in docs_data}

        # Deactivate only the original four inline seed documents. Never deactivate arbitrary
        # knowledge created later through CRUD/admin workflows just because it is not in the
        # repository PDF manifest.
        legacy_seed_titles = {
            "Fasting Guidelines for Diagnostic Blood Tests",
            "Home Sample Collection Process & Service Areas",
            "Appointment Cancellation & Rescheduling Policy",
            "Turnaround Times and Result Delivery",
        }
        all_existing = db.session.execute(select(KnowledgeDocument)).scalars().all()
        for old_doc in all_existing:
            if (
                old_doc.title in legacy_seed_titles
                and old_doc.title not in manifest_titles
                and old_doc.active
            ):
                old_doc.active = False
                db.session.flush()

    else:
        docs_data = [
            {
                "title": "Fasting Guidelines for Diagnostic Blood Tests",
                "category": "Preparation",
                "content": (
                    "Fasting instructions for diagnostic tests: For Lipid Profile, complete fasting "
                    "for 10 to 12 hours is required (water is permitted). For Fasting Blood Sugar (FBS), "
                    "an 8-hour fast is required. Coffee, tea, milk, juices, and smoking are strictly "
                    "prohibited during the fasting period. For medication-related preparation, follow "
                    "the instructions provided by your laboratory or qualified healthcare professional."
                ),
                "version": 1,
                "active": True,
            },
            {
                "title": "Home Sample Collection Process & Service Areas",
                "category": "Services",
                "content": (
                    "MediLab provides professional home sample collection across Greater Cairo including "
                    "Nasr City, Heliopolis, Maadi, Dokki, Mohandessin, and New Cairo. A certified phlebotomist "
                    "arrives during your reserved time slot equipped with sterile collection equipment "
                    "and cold-chain transport containers to guarantee pre-analytical sample integrity."
                ),
                "version": 1,
                "active": True,
            },
            {
                "title": "Appointment Cancellation & Rescheduling Policy",
                "category": "Policies",
                "content": (
                    "Branch appointments may be rescheduled or cancelled up to 2 hours prior to the "
                    "scheduled appointment time. Home collection visits can be cancelled or rescheduled up "
                    "to 4 hours prior to the scheduled slot. Cancellations made within policy guidelines "
                    "incur zero fees and immediately release reserved phlebotomy capacity."
                ),
                "version": 1,
                "active": True,
            },
            {
                "title": "Turnaround Times and Result Delivery",
                "category": "FAQ",
                "content": (
                    "Standard routine tests (CBC, Glucose, Kidney, Liver, Urine) are reported within 2 to 5 hours "
                    "from sample receipt. Specialized tests such as TSH are reported within 24 hours, and Vitamin D "
                    "within 48 hours. Official certified results are sent via WhatsApp notification, email, and "
                    "available on the MediLab patient portal."
                ),
                "version": 1,
                "active": True,
            },
        ]

    seeded: dict[str, KnowledgeDocument] = {}
    for item in docs_data:
        doc = db.session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.title == item["title"])
        ).scalar_one_or_none()
        if doc is None:
            doc = KnowledgeDocument(
                title=item["title"],
                category=item["category"],
                content=item["content"],
                active=item.get("active", True),
                version=item.get("version", 1),
                index_status="PENDING",
            )
            db.session.add(doc)
            db.session.flush()
        else:
            # The PDF corpus owns canonical document content once ingestion has occurred.
            # Seed may synchronize stable manifest metadata, but it must never overwrite the
            # parsed PDF text or invalidate READY chunks with a bootstrap placeholder.
            doc.category = item["category"]
            doc.active = item.get("active", True)
            if not (doc.content or "").strip():
                doc.content = item["content"]
            if not doc.index_status:
                doc.index_status = "PENDING"
            db.session.flush()
        seeded[item["title"]] = doc

    return seeded


def run_seed() -> dict[str, int]:
    """Execute all seed routines within a single transaction and return entity counts."""
    print("Starting MediLab AI database seeding...")
    categories = seed_categories()
    tests = seed_lab_tests(categories)
    packages = seed_packages(tests)
    branches = seed_branches()
    seed_availability_slots(branches)
    docs = seed_knowledge_documents()

    db.session.commit()

    # Query authoritative counts from the database
    counts = {
        "categories": len(categories),
        "lab_tests": len(tests),
        "packages": len(packages),
        "branches": len(branches),
        "availability_slots": db.session.execute(
            select(db.func.count(AvailabilitySlot.id))
        ).scalar()
        or 0,
        "knowledge_documents": len(docs),
    }

    print("-" * 50)
    print("MediLab AI Database Seeding Complete:")
    for entity, count in counts.items():
        print(f"  {entity:22}: {count}")
    print("-" * 50)
    return counts


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        run_seed()
