"""Thin customer UI routes backed by existing MediLab services and agent."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from flask import current_app, jsonify, render_template, request, session

from app.agent.graph import MediLabAgent
from app.blueprints.customer import customer_bp
from app.repositories.conversation_repository import ConversationRepository
from app.services.branch_service import BranchService
from app.services.package_service import PackageService
from app.services.test_service import TestService

logger = logging.getLogger("medilab.customer")


def _session_id() -> str:
    """Return the durable conversation identifier held in the signed session cookie."""
    session_id = session.get("medilab_session_id")
    if not session_id:
        session_id = f"web-{uuid4().hex}"
        session["medilab_session_id"] = session_id
    return str(session_id)


def _agent() -> MediLabAgent:
    """Create one compiled agent per Flask application process."""
    agent = current_app.extensions.get("medilab_agent")
    if agent is None:
        agent = MediLabAgent()
        current_app.extensions["medilab_agent"] = agent
    return agent


def _opening_hours(value: dict[str, Any] | None) -> str:
    if not value:
        return "Hours available from the assistant"
    if "open" in value and "close" in value:
        return f"{value['open']}–{value['close']}"
    values = [f"{day.title()}: {hours}" for day, hours in value.items() if hours]
    return " · ".join(values) or "Hours available from the assistant"


def _history(session_id: str) -> list[dict[str, Any]]:
    conversation = ConversationRepository().get_session(session_id)
    if conversation is None:
        return []
    return [
        {
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
            "metadata": message.metadata_ or {},
        }
        for message in conversation.messages
        if message.role in {"user", "assistant"}
    ]


def _catalog_context(*, query: str | None = None, category: str | None = None) -> dict[str, Any]:
    min_price = request.args.get("min_price", type=str)
    max_price = request.args.get("max_price", type=str)
    try:
        parsed_min = Decimal(min_price) if min_price else None
        parsed_max = Decimal(max_price) if max_price else None
    except InvalidOperation:
        parsed_min = parsed_max = None
    return {
        "tests": TestService().search_tests(
            query=query,
            category_slug=category or None,
            min_price=parsed_min,
            max_price=parsed_max,
        ),
        "categories": TestService().list_categories(),
    }


@customer_bp.get("/")
def home() -> str:
    data_error = False
    try:
        popular_tests = TestService().search_tests()[:3]
        popular_packages = PackageService().search_packages()[:2]
        branches = BranchService().list_active_branches()[:3]
    except Exception:
        logger.warning("Customer homepage catalog data unavailable", exc_info=True)
        popular_tests, popular_packages, branches, data_error = [], [], [], True
    return render_template(
        "customer/home.html",
        popular_tests=popular_tests,
        popular_packages=popular_packages,
        branches=branches,
        data_error=data_error,
        opening_hours=_opening_hours,
    )


@customer_bp.get("/tests")
def tests_catalog() -> str:
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    data_error = False
    try:
        context = _catalog_context(query=query or None, category=category or None)
    except Exception:
        logger.warning("Customer test catalog unavailable", exc_info=True)
        context, data_error = {"tests": [], "categories": []}, True
    return render_template(
        "customer/tests.html",
        query=query,
        selected_category=category,
        data_error=data_error,
        **context,
    )


@customer_bp.get("/packages")
def packages_catalog() -> str:
    query = request.args.get("q", "").strip()
    data_error = False
    try:
        packages = PackageService().search_packages(query=query or None)
    except Exception:
        logger.warning("Customer package catalog unavailable", exc_info=True)
        packages, data_error = [], True
    return render_template(
        "customer/packages.html", packages=packages, query=query, data_error=data_error
    )


@customer_bp.get("/branches")
def branches() -> str:
    data_error = False
    try:
        branch_rows = BranchService().list_active_branches()
    except Exception:
        logger.warning("Customer branch catalog unavailable", exc_info=True)
        branch_rows, data_error = [], True
    return render_template(
        "customer/branches.html",
        branches=branch_rows,
        opening_hours=_opening_hours,
        data_error=data_error,
    )


@customer_bp.get("/chat")
def chat() -> str:
    session_id = _session_id()
    try:
        history = _history(session_id)
    except Exception:
        logger.warning("Customer conversation history unavailable", exc_info=True)
        history = []
    return render_template("customer/chat.html", messages=history)


@customer_bp.post("/api/chat")
def chat_api():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify(
            {"error": {"code": "invalid_message", "message": "Please enter a message."}}
        ), 400
    if len(message) > int(current_app.config["MAX_INPUT_LENGTH"]):
        return jsonify(
            {
                "error": {
                    "code": "message_too_long",
                    "message": "That message is too long. Please shorten it and try again.",
                }
            }
        ), 400

    try:
        result = _agent().run_turn(session_id=_session_id(), message=message.strip())
        return jsonify(
            {
                "session_id": result.get("session_id"),
                "response": result.get("response") or "I’m sorry, I couldn’t prepare a response.",
                "structured_result": result.get("structured_result") or {},
                "visible_results": (result.get("active_search_snapshot") or {}).get("items", []),
                "action_result": result.get("action_result"),
                "pending_action": bool(result.get("pending_action")),
            }
        )
    except Exception:
        logger.error("Customer chat request failed", exc_info=True)
        return jsonify(
            {
                "error": {
                    "code": "assistant_unavailable",
                    "message": "MediLab AI is temporarily unavailable. Your message was not sent; please try again.",
                }
            }
        ), 503


@customer_bp.get("/booking-status")
def booking_status() -> str:
    _session_id()
    return render_template("customer/booking_status.html")
