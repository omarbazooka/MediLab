"""Unit tests for Phase 1 service business logic."""

from __future__ import annotations

import re

from app.services.booking_service import BookingService


def test_booking_reference_generation_format() -> None:
    """Verify that generated booking references conform to MLB-YYYYMMDD-XXXX format."""
    ref = BookingService.generate_booking_reference()
    pattern = r"^MLB-\d{8}-[A-Z0-9]{4}$"
    assert re.match(pattern, ref), f"Reference '{ref}' does not match expected pattern {pattern}"


def test_booking_reference_uniqueness() -> None:
    """Verify generated booking references are unique."""
    refs = {BookingService.generate_booking_reference() for _ in range(50)}
    assert len(refs) == 50
