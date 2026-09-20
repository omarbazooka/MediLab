"""Action execution and multi-turn pending business action handler for MediLab AI."""

from __future__ import annotations

import time
from datetime import date
from datetime import time as dt_time
from typing import Any

from app.agent.pending_action import (
    build_confirmation_summary,
    create_initial_pending_action,
    generate_action_idempotency_key,
    is_cancellation_intent,
    is_confirmation_message,
    merge_extracted_into_pending,
    validate_and_recompute_missing,
)
from app.agent.schemas import AgentIntent
from app.agent.state import MediLabAgentState
from app.repositories.branch_repository import BranchRepository
from app.repositories.package_repository import PackageRepository
from app.repositories.test_repository import TestRepository
from app.services.booking_service import (
    BookingNotFoundError,
    BookingService,
    BookingValidationError,
    CapacityExceededError,
    SlotUnavailableError,
)


def _resolve_entities_from_catalog(
    pending: dict[str, Any],
    entities: dict[str, Any],
    user_message: str,
    test_repo: TestRepository,
    package_repo: PackageRepository,
    branch_repo: BranchRepository,
) -> dict[str, Any]:
    """Deterministically resolve test, package, and branch IDs from user query/entities."""
    updated = dict(pending)
    lower = user_message.lower()

    # 1. Resolve test or package if not already resolved
    if not updated.get("test_id") and not updated.get("package_id"):
        test_query = entities.get("test_query")
        package_query = entities.get("package_query")

        # Code matches
        for code in [
            "CBC",
            "LIPID",
            "LFT",
            "KFT",
            "TSH",
            "VITD",
            "FERRITIN",
            "HBA1C",
            "FBS",
            "URINE",
        ]:
            if code.lower() in lower or (test_query and code.lower() in str(test_query).lower()):
                found = test_repo.get_by_code(code)
                if found:
                    updated["test_id"] = found.id
                    updated["test_name"] = found.name
                    break

        if not updated.get("test_id") and not updated.get("package_id"):
            if test_query and isinstance(test_query, str):
                tests = test_repo.search(test_query.strip())
                if tests:
                    updated["test_id"] = tests[0].id
                    updated["test_name"] = tests[0].name
            elif package_query and isinstance(package_query, str):
                pkgs = package_repo.search(package_query.strip())
                if pkgs:
                    updated["package_id"] = pkgs[0].id
                    updated["package_name"] = pkgs[0].name

    # 2. Resolve branch if not already resolved
    if updated.get("visit_type") == "BRANCH" and not updated.get("branch_id"):
        branches = branch_repo.list_active_branches()
        branch_query = str(
            entities.get("branch_name") or entities.get("branch_query") or ""
        ).lower()

        for b in branches:
            b_name_lower = b.name.lower()
            if b_name_lower in lower or (branch_query and b_name_lower in branch_query):
                updated["branch_id"] = b.id
                updated["branch_name"] = b.name
                break
            # Specific branch aliases
            if "nasr city" in lower or "مدينة نصر" in lower:
                if "nasr city" in b_name_lower:
                    updated["branch_id"] = b.id
                    updated["branch_name"] = b.name
                    break
            elif "maadi" in lower or "المعادي" in lower or "معادي" in lower:
                if "maadi" in b_name_lower:
                    updated["branch_id"] = b.id
                    updated["branch_name"] = b.name
                    break
            elif "dokki" in lower or "الدقي" in lower or "دقي" in lower:
                if "dokki" in b_name_lower:
                    updated["branch_id"] = b.id
                    updated["branch_name"] = b.name
                    break
            elif "new cairo" in lower or "التجمع" in lower or "القاهرة الجديدة" in lower:
                if "new cairo" in b_name_lower:
                    updated["branch_id"] = b.id
                    updated["branch_name"] = b.name
                    break

    return updated


def action_boundary_node(state: MediLabAgentState) -> dict[str, Any]:
    """Execute business actions, enforce 30m slots, and manage multi-turn pending actions."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("action_boundary_node")

    session_id = state.get("session_id", "")
    user_msg = state.get("normalized_user_message") or state.get("user_message", "")
    intent = state.get("intent") or ""
    entities = dict(state.get("entities", {}))
    existing_pending = state.get("pending_action")
    customer_id = state.get("customer_id")
    customer_context = state.get("customer_context") or {}
    session_phone = customer_context.get("phone")

    booking_service = BookingService()
    test_repo = TestRepository()
    package_repo = PackageRepository()
    branch_repo = BranchRepository()

    active_selection = {
        "selected_test_id": state.get("selected_test_id"),
        "selected_test_name": state.get("selected_test_name"),
        "selected_package_id": state.get("selected_package_id"),
        "selected_package_name": state.get("selected_package_name"),
    }

    # =========================================================================
    # 1. READ ACTION: Booking Status Check (get_booking_status)
    # =========================================================================
    if intent == AgentIntent.CHECK_BOOKING.value and not existing_pending:
        ref = entities.get("booking_reference")
        if not ref:
            import re

            m = re.search(r"\b(MLB-\d{8}-[A-F0-9]{8})\b", user_msg, re.IGNORECASE)
            if m:
                ref = m.group(1).upper()

        if not ref:
            timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
            return {
                "action_result": {
                    "action_type": "CHECK_BOOKING",
                    "status": "NEEDS_DATA",
                    "missing_fields": ["booking_reference"],
                    "committed": False,
                    "success": False,
                    "message": "Please provide your booking reference (e.g. MLB-20260920-XXXXXXXX) to check its status.",
                },
                "pending_action": None,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }

        booking = booking_service.get_booking_status(
            reference=ref,
            customer_id=customer_id,
            customer_phone=session_phone,
        )
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000

        if booking is None:
            return {
                "action_result": {
                    "action_type": "CHECK_BOOKING",
                    "status": "STATUS_NOT_FOUND",
                    "committed": False,
                    "success": False,
                    "booking_reference": ref,
                    "message": f"No booking found with reference '{ref}' in your account.",
                },
                "pending_action": None,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }

        items_desc = ", ".join(
            (item.test.name if item.test else item.package.name if item.package else "Item")
            for item in booking.items
        )
        return {
            "action_result": {
                "action_type": "CHECK_BOOKING",
                "status": "STATUS_FOUND",
                "committed": False,
                "success": True,
                "booking": {
                    "reference": booking.booking_reference,
                    "status": booking.status,
                    "visit_type": booking.visit_type,
                    "branch_name": booking.branch.name if booking.branch else None,
                    "scheduled_date": booking.scheduled_date.isoformat(),
                    "scheduled_time": booking.scheduled_time.strftime("%H:%M"),
                    "items": items_desc,
                    "total_price": f"{booking.total_price:.2f}",
                },
            },
            "pending_action": None,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }

    # =========================================================================
    # 2. CANCEL ACTION: Booking Cancellation (cancel_booking)
    # =========================================================================
    if intent == AgentIntent.CANCEL_BOOKING.value or (
        existing_pending and existing_pending.get("action_type") == "CANCEL_BOOKING"
    ):
        pending = existing_pending or create_initial_pending_action("CANCEL_BOOKING", session_id)
        pending = merge_extracted_into_pending(pending, entities, user_msg)
        pending = validate_and_recompute_missing(pending, booking_service)

        ref = pending.get("booking_reference")
        if not ref:
            timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
            return {
                "action_result": {
                    "action_type": "CANCEL_BOOKING",
                    "status": "NEEDS_DATA",
                    "missing_fields": ["booking_reference"],
                    "committed": False,
                    "success": False,
                    "message": "Please provide the booking reference code you wish to cancel.",
                },
                "pending_action": pending,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }

        # Check booking existence and ownership
        booking = booking_service.get_booking_status(
            reference=ref,
            customer_id=customer_id,
            customer_phone=session_phone,
        )
        if booking is None:
            timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
            return {
                "action_result": {
                    "action_type": "CANCEL_BOOKING",
                    "status": "ERROR",
                    "committed": False,
                    "success": False,
                    "booking_reference": ref,
                    "message": f"Could not find booking reference '{ref}' belonging to your account.",
                },
                "pending_action": None,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }

        if booking.status == "CANCELLED":
            timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
            return {
                "action_result": {
                    "action_type": "CANCEL_BOOKING",
                    "status": "ALREADY_CANCELLED",
                    "committed": False,
                    "success": True,
                    "booking_reference": ref,
                    "message": f"Booking '{ref}' is already cancelled.",
                },
                "pending_action": None,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }

        # Check if user explicitly confirmed cancellation
        confirmed = is_confirmation_message(user_msg, action_type="CANCEL_BOOKING")
        if not confirmed:
            items_desc = ", ".join(
                (item.test.name if item.test else item.package.name if item.package else "Item")
                for item in booking.items
            )
            timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
            return {
                "action_result": {
                    "action_type": "CANCEL_BOOKING",
                    "status": "AWAITING_CONFIRMATION",
                    "committed": False,
                    "success": False,
                    "booking_reference": ref,
                    "summary": {
                        "booking_reference": ref,
                        "scheduled_date": booking.scheduled_date.isoformat(),
                        "scheduled_time": booking.scheduled_time.strftime("%H:%M"),
                        "service_name": items_desc,
                    },
                    "message": f"Are you sure you want to cancel booking {ref} ({items_desc} on {booking.scheduled_date} at {booking.scheduled_time.strftime('%H:%M')})?",
                },
                "pending_action": pending,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }

        # User confirmed cancellation -> Execute atomic cancellation
        try:
            cancelled_booking = booking_service.cancel_booking(
                reference=ref,
                customer_id=customer_id,
                customer_phone=session_phone,
            )
            timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
            return {
                "action_result": {
                    "action_type": "CANCEL_BOOKING",
                    "status": "CANCELLED",
                    "committed": True,
                    "success": True,
                    "booking_reference": cancelled_booking.booking_reference,
                    "message": f"Booking {cancelled_booking.booking_reference} has been successfully cancelled, and the slot has been released.",
                },
                "pending_action": None,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }
        except (BookingNotFoundError, BookingValidationError) as e:
            timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
            return {
                "action_result": {
                    "action_type": "CANCEL_BOOKING",
                    "status": "ERROR",
                    "committed": False,
                    "success": False,
                    "booking_reference": ref,
                    "message": str(e),
                },
                "pending_action": None,
                "response_goal": "ANSWER",
                "route_trace": routes,
                "node_timings": timings,
            }

    # =========================================================================
    # 3. MUTATING ACTIONS: Create Branch Booking / Home Visit
    # =========================================================================
    # User aborted in-flight pending action
    if existing_pending and is_cancellation_intent(user_msg):
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
        return {
            "action_result": {
                "action_type": existing_pending.get("action_type", "BOOKING"),
                "status": "ABORTED",
                "committed": False,
                "success": False,
                "message": "The booking process has been cancelled.",
            },
            "pending_action": None,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }

    # Determine action type
    if existing_pending:
        pending = dict(existing_pending)
    else:
        action_type = (
            "CREATE_HOME_VISIT"
            if intent == AgentIntent.BOOK_HOME_VISIT.value
            else "CREATE_BRANCH_BOOKING"
        )
        visit_type = "HOME" if action_type == "CREATE_HOME_VISIT" else "BRANCH"
        pending = create_initial_pending_action(action_type, session_id, visit_type=visit_type)

    # Merge extracted entities and resolve catalog references
    pending = merge_extracted_into_pending(pending, entities, user_msg, active_selection)
    pending = _resolve_entities_from_catalog(
        pending, entities, user_msg, test_repo, package_repo, branch_repo
    )
    pending = validate_and_recompute_missing(pending, booking_service)

    # 3A. Slot is invalid (off-grid, outside opening hours) or fully booked
    if pending.get("slot_error"):
        summary = build_confirmation_summary(pending, booking_service)
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
        return {
            "action_result": {
                "action_type": pending["action_type"],
                "status": "SLOT_ERROR",
                "committed": False,
                "success": False,
                "reason": pending["slot_error"],
                "alternatives": pending.get("alternatives", []),
                "summary": summary,
                "message": f"{pending['slot_error']} Please choose from our available slots.",
            },
            "pending_action": pending,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }

    # 3B. Missing required fields -> Ask targeted question
    if pending.get("missing_fields"):
        summary = build_confirmation_summary(pending, booking_service)
        first_missing = pending["missing_fields"][0]
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
        return {
            "action_result": {
                "action_type": pending["action_type"],
                "status": "NEEDS_DATA",
                "committed": False,
                "success": False,
                "missing_fields": pending["missing_fields"],
                "next_required": first_missing,
                "summary": summary,
            },
            "pending_action": pending,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }

    # 3C. All fields collected -> Check explicit confirmation
    summary = build_confirmation_summary(pending, booking_service)
    pending["summary"] = summary
    if not pending.get("idempotency_key"):
        pending["idempotency_key"] = generate_action_idempotency_key(session_id, pending)

    confirmed = is_confirmation_message(user_msg, action_type=pending["action_type"])

    # If NOT confirmed yet -> Present confirmation summary
    if not confirmed:
        pending["confirmation_state"] = "AWAITING_CONFIRMATION"
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
        c_name = summary.get("customer_name")
        c_phone = summary.get("customer_phone")
        c_info = f" for {c_name} ({c_phone})" if c_name else ""
        return {
            "action_result": {
                "action_type": pending["action_type"],
                "status": "AWAITING_CONFIRMATION",
                "committed": False,
                "success": False,
                "summary": summary,
                "message": (
                    f"Please confirm your booking for {summary['service_name']} at {summary['branch_name'] or summary['area']} "
                    f"on {summary['scheduled_date']} at {summary['scheduled_time']} for {summary['total_price']} EGP{c_info}. "
                    "Would you like me to confirm this appointment?"
                ),
            },
            "pending_action": pending,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }

    # 3D. User explicitly confirmed -> Execute transactional booking
    slot_id = pending["slot_id"]
    idemp_key = pending["idempotency_key"]

    try:
        if pending["visit_type"] == "BRANCH":
            booking = booking_service.create_branch_booking(
                customer_name=pending["customer_name"],
                customer_phone=pending["customer_phone"],
                branch_id=pending["branch_id"],
                slot_id=slot_id,
                idempotency_key=idemp_key,
                test_ids=[pending["test_id"]] if pending.get("test_id") else None,
                package_ids=[pending["package_id"]] if pending.get("package_id") else None,
                customer_email=pending.get("customer_email"),
                notes=pending.get("notes"),
            )
        else:
            booking = booking_service.create_home_visit(
                customer_name=pending["customer_name"],
                customer_phone=pending["customer_phone"],
                slot_id=slot_id,
                address=pending["address"],
                area=pending["area"],
                idempotency_key=idemp_key,
                test_ids=[pending["test_id"]] if pending.get("test_id") else None,
                package_ids=[pending["package_id"]] if pending.get("package_id") else None,
                home_instructions=pending.get("notes"),
                customer_email=pending.get("customer_email"),
                notes=pending.get("notes"),
            )

        ref = booking.booking_reference
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000

        return {
            "action_result": {
                "action_type": pending["action_type"],
                "status": "EXECUTED",
                "committed": True,
                "success": True,
                "booking_reference": ref,
                "summary": summary,
                "message": (
                    f"Your booking has been confirmed! Your booking reference is {ref}. "
                    f"Scheduled for {summary['service_name']} on {summary['scheduled_date']} at {summary['scheduled_time']}."
                ),
            },
            "pending_action": None,  # Action complete; clear pending state
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }

    except (CapacityExceededError, SlotUnavailableError) as e:
        # Controlled slot rejection (e.g. concurrent race won by another customer)
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
        # Re-check nearby alternatives
        target_d = (
            date.fromisoformat(pending["scheduled_date"])
            if pending.get("scheduled_date")
            else date(2026, 9, 21)
        )
        target_t = dt_time(16, 0)
        if pending.get("scheduled_time"):
            tp = [int(p) for p in pending["scheduled_time"].split(":")]
            target_t = dt_time(tp[0], tp[1])
        alt_slots = branch_repo.find_nearby_available_slots(
            target_date=target_d,
            target_time=target_t,
            branch_id=pending.get("branch_id"),
            visit_type=pending.get("visit_type", "BRANCH"),
            limit=3,
        )
        return {
            "action_result": {
                "action_type": pending["action_type"],
                "status": "SLOT_FULL",
                "committed": False,
                "success": False,
                "reason": str(e),
                "alternatives": [
                    {"slot_id": s.id, "date": s.date.isoformat(), "time": s.time.strftime("%H:%M")}
                    for s in alt_slots
                ],
                "message": f"Unfortunately this slot is no longer available: {str(e)}. Please select an alternative slot.",
            },
            "pending_action": pending,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }
    except BookingValidationError as e:
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
        return {
            "action_result": {
                "action_type": pending["action_type"],
                "status": "VALIDATION_ERROR",
                "committed": False,
                "success": False,
                "reason": str(e),
                "message": f"Booking validation error: {str(e)}",
            },
            "pending_action": pending,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }
    except Exception as e:
        timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000
        return {
            "action_result": {
                "action_type": pending["action_type"],
                "status": "ERROR",
                "committed": False,
                "success": False,
                "reason": str(e),
                "message": "An unexpected error occurred while processing your booking. Please try again.",
            },
            "pending_action": pending,
            "response_goal": "ANSWER",
            "route_trace": routes,
            "node_timings": timings,
        }
