"""Deterministic business service for booking creation, idempotency, and cancellation."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.booking import Booking, BookingItem
from app.models.home_visit import HomeVisit
from app.repositories.booking_repository import BookingRepository
from app.repositories.branch_repository import BranchRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.package_repository import PackageRepository
from app.repositories.test_repository import TestRepository

if TYPE_CHECKING:
    pass


class BookingValidationError(ValueError):
    """Raised when booking request data is missing, invalid, or inconsistent."""


class SlotUnavailableError(RuntimeError):
    """Raised when an availability slot cannot be found or is inactive."""


class CapacityExceededError(RuntimeError):
    """Raised when an availability slot is completely booked."""


class BookingNotFoundError(LookupError):
    """Raised when a booking reference cannot be found."""


class BookingService:
    """Business service governing appointment bookings, capacity locking, and idempotency."""

    def __init__(
        self,
        booking_repo: BookingRepository | None = None,
        branch_repo: BranchRepository | None = None,
        test_repo: TestRepository | None = None,
        package_repo: PackageRepository | None = None,
        customer_repo: CustomerRepository | None = None,
    ) -> None:
        self.booking_repo = booking_repo or BookingRepository()
        self.branch_repo = branch_repo or BranchRepository()
        self.test_repo = test_repo or TestRepository()
        self.package_repo = package_repo or PackageRepository()
        self.customer_repo = customer_repo or CustomerRepository()

    @staticmethod
    def generate_booking_reference() -> str:
        """Generate a collision-safe, human-readable booking reference.

        Example: MLB-20260912-7A3F9B1C
        """
        today_str = datetime.now(UTC).strftime("%Y%m%d")
        random_suffix = secrets.token_hex(4).upper()  # 8 hex characters
        return f"MLB-{today_str}-{random_suffix}"

    def create_booking(
        self,
        customer_name: str,
        customer_phone: str,
        slot_id: int,
        visit_type: str,
        idempotency_key: str,
        customer_email: str | None = None,
        branch_id: int | None = None,
        test_ids: list[int] | None = None,
        package_ids: list[int] | None = None,
        address: str | None = None,
        area: str | None = None,
        home_instructions: str | None = None,
        notes: str | None = None,
    ) -> Booking:
        """Create a booking in a single atomic transaction.

        Guarantees:
        - Idempotency: exact duplicate idempotency_key returns existing booking without mutation.
        - Capacity Protection: slot reserved_count is atomically checked and locked.
        - Rollback: any validation or database error leaves zero partial state.
        """
        # 1. Check idempotency key first
        clean_idempotency_key = idempotency_key.strip()
        if not clean_idempotency_key:
            raise BookingValidationError("idempotency_key is required.")

        existing_booking = self.booking_repo.get_by_idempotency_key(clean_idempotency_key)
        if existing_booking is not None:
            return existing_booking

        # 2. Basic validation
        if not customer_name or not customer_name.strip():
            raise BookingValidationError("customer_name is required.")
        if not customer_phone or not customer_phone.strip():
            raise BookingValidationError("customer_phone is required.")

        clean_visit_type = visit_type.strip().upper()
        if clean_visit_type not in {"BRANCH", "HOME"}:
            raise BookingValidationError(
                f"Invalid visit_type '{visit_type}'. Must be 'BRANCH' or 'HOME'."
            )

        test_ids = test_ids or []
        package_ids = package_ids or []
        if not test_ids and not package_ids:
            raise BookingValidationError("At least one test or package must be selected.")

        if clean_visit_type == "BRANCH" and branch_id is None:
            raise BookingValidationError("branch_id is required for BRANCH visits.")

        if clean_visit_type == "HOME":
            if not address or not address.strip():
                raise BookingValidationError("address is required for HOME visits.")
            if not area or not area.strip():
                raise BookingValidationError("area is required for HOME visits.")

        # Begin atomic transactional mutation
        try:
            # 3. Resolve and lock availability slot
            slot = self.branch_repo.get_slot_by_id(slot_id, for_update=True)
            if slot is None or not slot.active:
                raise SlotUnavailableError(
                    f"Availability slot {slot_id} does not exist or is inactive."
                )

            if slot.visit_type != clean_visit_type:
                raise BookingValidationError(
                    f"Slot visit_type '{slot.visit_type}' does not match requested visit_type '{clean_visit_type}'."
                )

            if clean_visit_type == "BRANCH" and slot.branch_id != branch_id:
                raise BookingValidationError("Slot branch does not match requested branch.")

            # 4. Strict capacity verification
            if slot.reserved_count >= slot.capacity:
                raise CapacityExceededError(
                    f"Slot {slot_id} has reached maximum capacity ({slot.capacity})."
                )

            # 5. Resolve or create customer
            customer = self.customer_repo.get_or_create(
                name=customer_name,
                phone=customer_phone,
                email=customer_email,
            )

            # 6. Resolve line items and snapshot prices
            booking_items: list[BookingItem] = []
            for tid in test_ids:
                lab_test = self.test_repo.get_by_id(tid)
                if lab_test is None or not lab_test.active:
                    raise BookingValidationError(f"Lab test {tid} does not exist or is inactive.")
                booking_items.append(
                    BookingItem(
                        test_id=lab_test.id,
                        unit_price_snapshot=lab_test.price,
                    )
                )

            for pid in package_ids:
                pkg = self.package_repo.get_by_id(pid)
                if pkg is None or not pkg.active:
                    raise BookingValidationError(f"Package {pid} does not exist or is inactive.")
                booking_items.append(
                    BookingItem(
                        package_id=pkg.id,
                        unit_price_snapshot=pkg.price,
                    )
                )

            # 7. Reserve slot capacity
            slot.reserved_count += 1

            # 8. Create booking record with limited reference collision retry
            MAX_REF_ATTEMPTS = 3
            booking = None
            for attempt in range(MAX_REF_ATTEMPTS):
                ref = self.generate_booking_reference()
                booking = Booking(
                    booking_reference=ref,
                    customer_id=customer.id,
                    availability_slot_id=slot.id,
                    visit_type=clean_visit_type,
                    branch_id=slot.branch_id if clean_visit_type == "BRANCH" else None,
                    scheduled_date=slot.date,
                    scheduled_time=slot.time,
                    status="CONFIRMED",
                    idempotency_key=clean_idempotency_key,
                    notes=notes.strip() if notes else None,
                    items=booking_items,
                )

                # 9. Create 1-to-1 HomeVisit details if applicable
                if clean_visit_type == "HOME":
                    booking.home_visit = HomeVisit(
                        address=address.strip(),
                        area=area.strip(),
                        instructions=home_instructions.strip() if home_instructions else None,
                        status="SCHEDULED",
                    )

                try:
                    with db.session.begin_nested():
                        self.booking_repo.add(booking)
                        db.session.flush()
                    break
                except IntegrityError as ie:
                    err_msg = str(ie).lower()
                    is_ref_collision = (
                        "bookings_booking_reference" in err_msg
                        or "key (booking_reference)" in err_msg
                    )
                    if is_ref_collision and attempt < MAX_REF_ATTEMPTS - 1:
                        continue
                    raise

            db.session.commit()
            return booking

        except IntegrityError:
            db.session.rollback()
            # Race condition: Did another concurrent worker commit with this exact idempotency key?
            existing_booking = self.booking_repo.get_by_idempotency_key(clean_idempotency_key)
            if existing_booking is not None:
                return existing_booking
            raise
        except Exception:
            db.session.rollback()
            raise

    def get_booking_by_reference(self, reference: str) -> Booking | None:
        """Fetch booking by its reference code."""
        if not reference or not reference.strip():
            return None
        return self.booking_repo.get_by_reference(reference)

    def cancel_booking(self, reference: str) -> Booking:
        """Cancel an existing booking and release slot capacity atomically.

        Locks the Booking row first to guarantee concurrent cancellation requests
        never decrement slot capacity multiple times.
        """
        if not reference or not reference.strip():
            raise BookingNotFoundError("Booking reference is required.")

        clean_ref = reference.strip().upper()
        try:
            # 1. Lock the booking row first with SELECT ... FOR UPDATE
            booking = self.booking_repo.get_by_reference(clean_ref, for_update=True)
            if booking is None:
                raise BookingNotFoundError(f"Booking reference '{reference}' not found.")

            # 2. Check cancellation status after acquiring lock
            if booking.status == "CANCELLED":
                db.session.commit()
                return booking

            # 3. Lock slot to release capacity safely
            slot = self.branch_repo.get_slot_by_id(booking.availability_slot_id, for_update=True)
            if slot and slot.reserved_count > 0:
                slot.reserved_count -= 1

            booking.status = "CANCELLED"
            booking.cancelled_at = datetime.now(UTC)

            if booking.home_visit:
                booking.home_visit.status = "CANCELLED"

            db.session.commit()
            return booking
        except Exception:
            db.session.rollback()
            raise
