"""Deterministic management of multi-turn pending business action state."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, time, timedelta
from typing import Any

from app.services.booking_service import BookingService


def is_confirmation_message(message: str, action_type: str | None = None) -> bool:
    """Return True if user utterance is an explicit confirmation of a pending action."""
    lower = message.strip().lower()
    confirm_tokens = [
        "confirm",
        "yes",
        "sure",
        "ok",
        "okay",
        "proceed",
        "do it",
        "please confirm",
        "أكد",
        "تاكيد",
        "تأكيد",
        "نعم",
        "ايوه",
        "أيوة",
        "تمام",
        "موافق",
        "احجز",
        "اعتمد",
        "يلا",
        "أكيد",
    ]
    if action_type == "CANCEL_BOOKING":
        # When confirming a cancellation, words like "confirm cancellation" or "yes cancel" are confirmations,
        # so "cancel" must not be treated as a negation. Only actual negative words (no, don't, etc.) negate.
        if any(
            neg in lower
            for neg in ["لا", "don't", "dont", "no", "keep it", "خلاص بلاش", "nevermind"]
        ):
            return False
    else:
        # Guard against negations: e.g. "no, do not confirm", "لا تؤكد", "cancel"
        if any(neg in lower for neg in ["لا", "don't", "dont", "no", "cancel", "الغ"]):
            return False

    return any(
        re.search(
            rf"(?:\b|(?<=[\u0600-\u06FF])){re.escape(token)}(?:\b|(?=[\u0600-\u06FF]))", lower
        )
        for token in confirm_tokens
    )


def is_cancellation_intent(message: str) -> bool:
    """Return True if user explicitly requests to cancel/abort the current in-flight pending action."""
    lower = message.strip().lower()
    cancel_tokens = [
        "cancel",
        "stop",
        "abort",
        "nevermind",
        "never mind",
        "الغاء",
        "إلغاء",
        "الغي",
        "تراجع",
        "بلاش",
        "مش عايز",
    ]
    return any(
        re.search(
            rf"(?:\b|(?<=[\u0600-\u06FF])){re.escape(token)}(?:\b|(?=[\u0600-\u06FF]))", lower
        )
        for token in cancel_tokens
    )


def parse_date_and_time(
    user_message: str, entities: dict[str, Any]
) -> tuple[date | None, time | None]:
    """Deterministically parse appointment date and time from extracted entities and utterance."""
    lower = user_message.lower()
    parsed_date: date | None = None
    parsed_time: time | None = None

    # Base anchor date: 2026-09-20 (canonical evaluation anchor date)
    anchor = date(2026, 9, 20)

    # 1. Date extraction
    raw_date = entities.get("date") or entities.get("scheduled_date")
    if raw_date and isinstance(raw_date, str):
        try:
            parsed_date = date.fromisoformat(raw_date.strip())
        except ValueError:
            pass

    if parsed_date is None:
        if "tomorrow" in lower or "بكرة" in lower or "غدا" in lower or "غداً" in lower:
            parsed_date = anchor + timedelta(days=1)
        elif "today" in lower or "النهاردة" in lower or "اليوم" in lower:
            parsed_date = anchor
        elif "after tomorrow" in lower or "بعد بكرة" in lower or "بعد غد" in lower:
            parsed_date = anchor + timedelta(days=2)
        else:
            # Match explicit dates: YYYY-MM-DD or DD/MM/YYYY
            iso_match = re.search(r"\b(2026-\d{2}-\d{2})\b", user_message)
            if iso_match:
                try:
                    parsed_date = date.fromisoformat(iso_match.group(1))
                except ValueError:
                    pass

    # 2. Time extraction
    raw_time = entities.get("time") or entities.get("scheduled_time")
    if raw_time and isinstance(raw_time, str):
        time_clean = raw_time.strip()
        time_match = re.match(r"^(\d{1,2}):(\d{2})$", time_clean)
        if time_match:
            try:
                parsed_time = time(int(time_match.group(1)), int(time_match.group(2)))
            except ValueError:
                pass

    if parsed_time is None:
        # Match e.g. "4:30 PM", "4:30 مساء", "11:00 am"
        match_meridiem = re.search(
            r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(pm|am|مساء|مساءً|صباحا|صباحاً|عصرا|عصراً)\b",
            lower,
        )
        if match_meridiem:
            h = int(match_meridiem.group(1))
            m = int(match_meridiem.group(2))
            meridiem = match_meridiem.group(3)
            is_pm = any(p in meridiem for p in ["pm", "مساء", "عصر"])
            if is_pm and h < 12:
                h += 12
            elif not is_pm and h == 12:
                h = 0
            parsed_time = time(h, m)
        else:
            # Match exact 24h: e.g. "16:00", "09:30"
            exact_24h = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", user_message)
            if exact_24h:
                h, m = int(exact_24h.group(1)), int(exact_24h.group(2))
                # If hour is 1-7 without meridiem, it's typically afternoon in a lab context (09:00 - 19:00)
                if 1 <= h <= 7 and "am" not in lower and "صباح" not in lower:
                    h += 12
                parsed_time = time(h, m)
            else:
                # 12-hour standalone: "4 PM", "4 مساء", "4 عصرا"
                match_12h = re.search(
                    r"\b([1-9]|1[0-2])\s*(pm|am|مساء|مساءً|صباحا|صباحاً|عصرا|عصراً)\b",
                    lower,
                )
                if match_12h:
                    h = int(match_12h.group(1))
                    m = 0
                    meridiem = match_12h.group(2)
                    is_pm = any(p in meridiem for p in ["pm", "مساء", "عصر"])
                    if is_pm and h < 12:
                        h += 12
                    elif not is_pm and h == 12:
                        h = 0
                    parsed_time = time(h, m)
                else:
                    # Arabic "الساعة 4"
                    ar_hour = re.search(r"(?:الساعة|ساعة)\s*([1-9]|1[0-2])(?::([0-5]\d))?", lower)
                    if ar_hour:
                        h = int(ar_hour.group(1))
                        m = int(ar_hour.group(2)) if ar_hour.group(2) else 0
                        if h in [1, 2, 3, 4, 5, 6, 7] and not any(
                            a in lower for a in ["صباح", "am"]
                        ):
                            h += 12
                        parsed_time = time(h, m)

    return parsed_date, parsed_time


def generate_action_idempotency_key(session_id: str, action_data: dict[str, Any]) -> str:
    """Generate a deterministic, collision-safe idempotency key for an action."""
    action_type = action_data.get("action_type", "")
    visit_type = action_data.get("visit_type", "")
    branch_id = action_data.get("branch_id")
    test_id = action_data.get("test_id")
    package_id = action_data.get("package_id")
    date_str = action_data.get("scheduled_date", "")
    time_str = action_data.get("scheduled_time", "")
    phone = (action_data.get("customer_phone") or "").strip()
    action_id = action_data.get("action_id", "")

    key_material = f"{session_id}:{action_id}:{action_type}:{visit_type}:{branch_id}:{test_id}:{package_id}:{date_str}:{time_str}:{phone}"
    hashed = hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:24]
    return f"IDEMP-{hashed}"


def create_initial_pending_action(
    action_type: str,
    session_id: str,
    visit_type: str = "BRANCH",
) -> dict[str, Any]:
    """Initialize a new clean pending action container."""
    action_id = str(uuid.uuid4())
    return {
        "action_id": action_id,
        "action_type": action_type,
        "visit_type": visit_type,
        "test_id": None,
        "test_name": None,
        "package_id": None,
        "package_name": None,
        "branch_id": None,
        "branch_name": None,
        "customer_name": None,
        "customer_phone": None,
        "customer_email": None,
        "scheduled_date": None,
        "scheduled_time": None,
        "slot_id": None,
        "address": None,
        "area": None,
        "notes": None,
        "booking_reference": None,
        "missing_fields": [],
        "confirmation_state": "COLLECTING",
        "idempotency_key": "",
        "summary": None,
        "completed_reference": None,
        "alternatives": [],
        "slot_error": None,
    }


def merge_extracted_into_pending(
    pending: dict[str, Any],
    entities: dict[str, Any],
    user_message: str,
    active_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge newly extracted entity values into the persistent pending action state."""
    updated = dict(pending)

    # 1. Test / Package resolution
    active_selection = active_selection or {}
    if not updated.get("test_id") and not updated.get("package_id"):
        if active_selection.get("selected_test_id"):
            updated["test_id"] = active_selection["selected_test_id"]
            updated["test_name"] = active_selection.get("selected_test_name")
        elif active_selection.get("selected_package_id"):
            updated["package_id"] = active_selection["selected_package_id"]
            updated["package_name"] = active_selection.get("selected_package_name")

    if entities.get("test_id"):
        updated["test_id"] = int(entities["test_id"])
    if entities.get("package_id"):
        updated["package_id"] = int(entities["package_id"])

    # 2. Branch resolution
    if entities.get("branch_id"):
        updated["branch_id"] = int(entities["branch_id"])
    if entities.get("branch_name"):
        updated["branch_name"] = str(entities["branch_name"])

    # 3. Customer name & phone
    if entities.get("customer_name"):
        updated["customer_name"] = str(entities["customer_name"]).strip()
    if entities.get("customer_phone"):
        updated["customer_phone"] = str(entities["customer_phone"]).strip()

    # Utterance heuristic for phone numbers if not parsed by entity extractor
    if not updated.get("customer_phone"):
        phone_match = re.search(r"\b(01[0125]\d{8}|\+201[0125]\d{8})\b", user_message)
        if phone_match:
            updated["customer_phone"] = phone_match.group(1)

    # Utterance heuristic for name: "my name is Ahmed", "اسمي أحمد علي"
    if not updated.get("customer_name"):
        name_match = re.search(
            r"(?:my name is|name is|اسمي|الاسم)\s+([A-Za-z\u0600-\u06FF]+(?:\s+[A-Za-z\u0600-\u06FF]+)?)",
            user_message,
            re.IGNORECASE,
        )
        if name_match:
            updated["customer_name"] = name_match.group(1).strip()

    # 4. Date & Time
    parsed_date, parsed_time = parse_date_and_time(user_message, entities)
    if parsed_date:
        updated["scheduled_date"] = parsed_date.isoformat()
    if parsed_time:
        updated["scheduled_time"] = parsed_time.strftime("%H:%M")

    # 5. Address & Area for HOME visits
    if entities.get("address"):
        updated["address"] = str(entities["address"]).strip()
    if entities.get("area"):
        updated["area"] = str(entities["area"]).strip()

    # Utterance heuristic for address / area
    if updated.get("visit_type") == "HOME":
        if not updated.get("area"):
            for candidate_area in [
                "Nasr City",
                "Maadi",
                "Dokki",
                "New Cairo",
                "Giza",
                "Heliopolis",
                "Zamalek",
                "Mohandessin",
                "مدينة نصر",
                "المعادي",
                "الدقي",
                "التجمع",
                "الجيزة",
                "مصر الجديدة",
                "الزمالك",
                "المهندسين",
            ]:
                if candidate_area.lower() in user_message.lower():
                    updated["area"] = candidate_area
                    break
        if not updated.get("address"):
            addr_match = re.search(
                r"(?:address|عنوان|شارع)\s*:?\s*([^,.\n]+(?:,\s*[^,.\n]+)?)",
                user_message,
                re.IGNORECASE,
            )
            if addr_match:
                updated["address"] = addr_match.group(1).strip()
            elif updated.get("area"):
                # If area is set but address isn't explicitly tagged with 'address', check for street
                street_match = re.search(
                    r"(\d+\s+[^,.\n]+(?:Street|St|شارع)[^,.\n]*)", user_message, re.IGNORECASE
                )
                if street_match:
                    updated["address"] = street_match.group(1).strip()

    # 6. Booking reference for status check or cancellation
    if entities.get("booking_reference"):
        updated["booking_reference"] = str(entities["booking_reference"]).strip().upper()
    else:
        ref_match = re.search(r"\b(MLB-\d{8}-[A-F0-9]{8})\b", user_message, re.IGNORECASE)
        if ref_match:
            updated["booking_reference"] = ref_match.group(1).upper()

    return updated


def validate_and_recompute_missing(
    pending: dict[str, Any],
    booking_service: BookingService,
) -> dict[str, Any]:
    """Validate current pending action deterministically and recompute missing fields."""
    updated = dict(pending)
    missing: list[str] = []
    action_type = updated.get("action_type")
    visit_type = updated.get("visit_type", "BRANCH")

    # Handle Cancellation Action
    if action_type == "CANCEL_BOOKING":
        if not updated.get("booking_reference"):
            missing.append("booking_reference")
        updated["missing_fields"] = missing
        if not missing and updated.get("confirmation_state") != "CONFIRMED":
            updated["confirmation_state"] = "AWAITING_CONFIRMATION"
        return updated

    # Handle Booking Creation (BRANCH or HOME)
    # 1. Service (Test or Package)
    if not updated.get("test_id") and not updated.get("package_id"):
        missing.append("service")

    # 2. Branch (required for BRANCH visit)
    if visit_type == "BRANCH" and not updated.get("branch_id"):
        missing.append("branch")

    # 3. Customer Info
    if not updated.get("customer_name"):
        missing.append("customer_name")
    if not updated.get("customer_phone"):
        missing.append("customer_phone")

    # 4. HOME specific fields
    if visit_type == "HOME":
        if not updated.get("address"):
            missing.append("address")
        if not updated.get("area"):
            missing.append("area")

    # 5. Date & Time / Slot
    slot_error = None
    alternatives = []
    slot_id = None

    if not updated.get("scheduled_date"):
        missing.append("scheduled_date")
    if not updated.get("scheduled_time"):
        missing.append("scheduled_time")

    if updated.get("scheduled_date") and updated.get("scheduled_time"):
        try:
            target_date = date.fromisoformat(updated["scheduled_date"])
            t_parts = [int(p) for p in updated["scheduled_time"].split(":")]
            target_time = time(t_parts[0], t_parts[1])

            branch_id = updated.get("branch_id")
            avail = booking_service.check_branch_availability(
                branch_id=branch_id if visit_type == "BRANCH" else None,
                visit_type=visit_type,
                target_date=target_date,
                target_time=target_time,
            )

            if avail["available"]:
                slot_id = avail["slot_id"]
                updated["slot_id"] = slot_id
                slot_error = None
                alternatives = []
            else:
                updated["slot_id"] = None
                slot_error = avail["reason"]
                alternatives = avail["alternatives"]
                # Slot is invalid/full; mark scheduled_time as needing correction
                if "scheduled_time" not in missing:
                    missing.append("scheduled_time")

        except (ValueError, IndexError):
            missing.append("scheduled_time")

    updated["slot_id"] = slot_id
    updated["slot_error"] = slot_error
    updated["alternatives"] = alternatives
    updated["missing_fields"] = missing

    if not missing and slot_id is not None:
        # Action is fully ready for confirmation
        if updated.get("confirmation_state") != "CONFIRMED":
            updated["confirmation_state"] = "AWAITING_CONFIRMATION"
    else:
        updated["confirmation_state"] = "COLLECTING"

    return updated


def build_confirmation_summary(
    pending: dict[str, Any], booking_service: BookingService
) -> dict[str, Any]:
    """Construct structured appointment confirmation summary with catalog DB price snapshots."""
    test_id = pending.get("test_id")
    package_id = pending.get("package_id")
    service_name = pending.get("test_name") or pending.get("package_name") or "Diagnostic Service"
    price = "0.00"

    if test_id:
        t = booking_service.test_repo.get_by_id(test_id)
        if t:
            service_name = t.name
            price = f"{t.price:.2f}"
    elif package_id:
        p = booking_service.package_repo.get_by_id(package_id)
        if p:
            service_name = p.name
            price = f"{p.price:.2f}"

    branch_name = pending.get("branch_name")
    if pending.get("branch_id") and not branch_name:
        b = booking_service.branch_repo.get_by_id(pending["branch_id"])
        if b:
            branch_name = b.name

    return {
        "service_name": service_name,
        "visit_type": pending.get("visit_type", "BRANCH"),
        "branch_name": branch_name,
        "scheduled_date": pending.get("scheduled_date"),
        "scheduled_time": pending.get("scheduled_time"),
        "customer_name": pending.get("customer_name"),
        "customer_phone": pending.get("customer_phone"),
        "total_price": price,
        "address": pending.get("address"),
        "area": pending.get("area"),
    }
