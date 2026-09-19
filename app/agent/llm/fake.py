"""Deterministic fake LLM provider for reproducible unit and graph testing."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.agent.schemas import (
    AgentIntent,
    RequestPlan,
    ResponseDraft,
    ResponseGoal,
    SafetyCategory,
    SafetyClassification,
    ValidationOutcome,
)


class FakeLLMProvider:
    """Configurable test double implementing LLMProvider protocol."""

    def __init__(
        self,
        canned_safety: SafetyClassification | None = None,
        canned_plan: RequestPlan | None = None,
        canned_clarification: str | None = None,
        canned_composition: ResponseDraft | None = None,
        canned_validation: ValidationOutcome | None = None,
    ) -> None:
        self.canned_safety = canned_safety
        self.canned_plan = canned_plan
        self.canned_clarification = canned_clarification
        self.canned_composition = canned_composition
        self.canned_validation = canned_validation

        self.calls: list[dict[str, Any]] = []
        self.understanding_handler: Callable[[str, dict[str, Any] | None], RequestPlan] | None = (
            None
        )
        self.composition_handler: Callable[[dict[str, Any]], ResponseDraft] | None = None

    def classify_safety(
        self,
        user_message: str,
        recent_context: list[dict[str, Any]] | None = None,
    ) -> SafetyClassification:
        self.calls.append({"method": "classify_safety", "message": user_message})
        if self.canned_safety is not None:
            return self.canned_safety

        lower = user_message.lower()
        # Emergency chest pain / acute symptoms
        if any(w in lower for w in ["chest pain", "ألم في الصدر", "left arm", "emergency"]):
            return SafetyClassification(
                category=SafetyCategory.OTHER_CLINICAL_UNSAFE,
                confidence=0.99,
                reason="Emergency acute symptoms require immediate hospital evaluation.",
            )

        # Symptom-based test recommendation
        if any(
            w in lower
            for w in ["دوخة", "dizzy", "dizziness", "حاسس بدوخة", "عندي دوخة", "صداع", "headache"]
        ):
            return SafetyClassification(
                category=SafetyCategory.SYMPTOM_BASED_TEST_RECOMMENDATION,
                confidence=0.98,
                reason="User is asking for diagnostic test selection based on clinical symptoms.",
            )

        # Medical diagnosis / result interpretation
        if (
            any(w in lower for w in ["250", "260"])
            and any(w in lower for w in ["سكر", "glucose", "diabetes", "عندي"])
        ) or any(w in lower for w in ["interpret", "تشخيص", "do i have diabetes", "عندي سكر؟"]):
            return SafetyClassification(
                category=SafetyCategory.RESULT_INTERPRETATION,
                confidence=0.99,
                reason="User is asking for clinical laboratory result interpretation or medical diagnosis.",
            )

        # Medication advice
        if any(
            w in lower
            for w in [
                "medicine",
                "dosage",
                "dose",
                "دواء",
                "علاج",
                "جرعة",
                "levothyroxine",
                "statin",
                "insulin",
            ]
        ):
            return SafetyClassification(
                category=SafetyCategory.MEDICATION_ADVICE,
                confidence=0.99,
                reason="User is asking for medication prescription or pharmacological advice.",
            )

        return SafetyClassification(
            category=SafetyCategory.SAFE_OPERATIONAL,
            confidence=1.0,
            reason="Operational inquiry suitable for lab customer service.",
        )

    def understand_request(
        self,
        user_message: str,
        context_summary: dict[str, Any] | None = None,
    ) -> RequestPlan:
        self.calls.append(
            {
                "method": "understand_request",
                "message": user_message,
                "context": context_summary,
            }
        )
        if self.understanding_handler is not None:
            return self.understanding_handler(user_message, context_summary)
        if self.canned_plan is not None:
            return self.canned_plan

        lower = user_message.lower()
        lang = "ar" if re.search(r"[\u0600-\u06FF]", user_message) else "en"

        # Out-of-domain queries
        if any(
            w in lower
            for w in ["repair", "laptop", "smartphone", "شاشة", "صيدلية", "بنادول", "panadol"]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.UNKNOWN_AMBIGUOUS,
                language=lang,
            )

        # Prompt injection defense boundary
        if any(
            w in lower
            for w in [
                "ignore all previous",
                "system prompt",
                "database password",
                "تجاهل كل التعليمات",
            ]
        ):
            if "cbc" in lower or "5 جنيه" in lower:
                return RequestPlan(
                    primary_intent=AgentIntent.TEST_PRICE,
                    requested_information=["price"],
                    entities={"test_query": "CBC"},
                    requires_structured_data=True,
                    language=lang,
                )
            return RequestPlan(
                primary_intent=AgentIntent.GENERAL_CONVERSATION,
                language=lang,
            )

        # General conversation / greetings / capabilities (must precede generic question words)
        if any(
            w in lower
            for w in [
                "hello",
                "hi",
                "hey",
                "good morning",
                "good evening",
                "thanks",
                "thank you",
                "أهلا",
                "اهلا",
                "مرحبا",
                "صباح الخير",
                "مساء الخير",
                "شكرا",
                "خدمات المعمل",
                "help me with today",
            ]
        ) and not any(
            w in lower for w in ["fast", "صيام", "سعر", "bkam", "بكام", "price", "how much", "cost"]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.GENERAL_CONVERSATION,
                language=lang,
            )

        # Customer history questions
        if any(
            w in lower
            for w in [
                "what did i book",
                "did i book",
                "last appointment",
                "حجزت إيه",
                "حجوزاتي",
                "last time",
                "history",
                "آخر حجز",
                "booked",
                "previous booking",
            ]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.CUSTOMER_HISTORY,
                requires_customer_history=True,
                language=lang,
            )

        # Policy questions
        if any(
            w in lower
            for w in [
                "policy",
                "reschedul",
                "النتائج",
                "whatsapp",
                "واتساب",
                "استلم",
                "غرامة",
                "رسوم",
                "ساعتين",
            ]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.POLICY,
                requested_information=["policy"],
                requires_rag=True,
                language=lang,
            )

        # Action boundary intents
        if any(w in lower for w in ["book", "احجز", "حجز"]):
            if any(w in lower for w in ["home", "منزلي", "البيت"]):
                return RequestPlan(
                    primary_intent=AgentIntent.BOOK_HOME_VISIT,
                    action_intent="BOOK_HOME_VISIT",
                    language=lang,
                )
            return RequestPlan(
                primary_intent=AgentIntent.BOOK_BRANCH_VISIT,
                action_intent="BOOK_BRANCH_VISIT",
                language=lang,
            )
        if any(w in lower for w in ["cancel", "إلغاء", "الغي"]):
            return RequestPlan(
                primary_intent=AgentIntent.CANCEL_BOOKING,
                action_intent="CANCEL_BOOKING",
                language=lang,
            )
        if any(w in lower for w in ["my booking", "status", "حالة الحجز"]):
            return RequestPlan(
                primary_intent=AgentIntent.CHECK_BOOKING,
                action_intent="CHECK_BOOKING",
                language=lang,
            )

        # Ordinal reference or selection
        ordinal_match = None
        if any(w in lower for w in ["first", "الأول", "الاول", "الأولاني", "1"]):
            ordinal_match = 1
        elif any(w in lower for w in ["second", "التاني", "الثاني", "2", "full"]):
            ordinal_match = 2
        elif any(w in lower for w in ["third", "التالت", "الثالث", "3"]):
            ordinal_match = 3

        if ordinal_match and context_summary and context_summary.get("has_active_snapshot"):
            return RequestPlan(
                primary_intent=AgentIntent.TEST_DETAILS,
                requires_structured_data=True,
                entities={"ordinal_ref": ordinal_match},
                references=["ordinal_selection"],
                language=lang,
            )

        # Package inquiry
        if any(w in lower for w in ["package", "packages", "باقة", "باقات", "checkup", "فحص شامل"]):
            if any(w in lower for w in ["price", "سعر", "بكام", "فيها", "tests", "تحاليل"]):
                return RequestPlan(
                    primary_intent=AgentIntent.PACKAGE_DETAILS,
                    requested_information=["price", "tests"],
                    entities={"package_query": "Comprehensive Health Checkup"},
                    requires_structured_data=True,
                    language=lang,
                )
            return RequestPlan(
                primary_intent=AgentIntent.PACKAGE_SEARCH,
                entities={"package_query": "all"},
                requires_structured_data=True,
                language=lang,
            )

        # Branch inquiry
        if any(
            w in lower
            for w in [
                "branch",
                "فرع",
                "فروع",
                "location",
                "address",
                "معادي",
                "maadi",
                "مدينة نصر",
                "cairo",
            ]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.BRANCH_INFO,
                requires_structured_data=True,
                entities={"branch_query": "all"},
                language=lang,
            )

        # Broad ambiguous category inquiries (e.g. "I want a thyroid test" or "تحليل سكر")
        if any(w in lower for w in ["thyroid", "غدة", "الغدة"]) and not any(
            w in lower for w in ["tsh", "fast", "صيام", "bkam", "بكام", "سعر"]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.TEST_SEARCH,
                requires_structured_data=True,
                entities={"test_query": "thyroid"},
                needs_clarification=True,
                clarification_target="test_selection",
                language=lang,
            )
        if any(w in lower for w in ["تحليل سكر", "sugar test"]) and not any(
            w in lower for w in ["hba1c", "fbs", "تراكمي", "صائم", "price", "سعر"]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.TEST_SEARCH,
                requires_structured_data=True,
                entities={"test_query": "sugar"},
                needs_clarification=True,
                clarification_target="test_selection",
                language=lang,
            )

        # RAG policy questions
        if any(
            w in lower for w in ["policy", "reschedul", "النتائج", "whatsapp", "واتساب", "استلم"]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.POLICY,
                requested_information=["policy"],
                requires_rag=True,
                language=lang,
            )

        # Combined SQL + RAG inquiries
        has_catalog_aspect = any(
            w in lower
            for w in [
                "what is",
                "price",
                "how much",
                "cost",
                "بكام",
                "سعر",
                "تمن",
                "إيه هو",
                "عبارة عن إيه",
                "turnaround",
                "ready",
            ]
        )
        has_rag_aspect = any(
            w in lower
            for w in ["fast", "fasting", "صيام", "تحضير", "prep", "preparation", "policy", "شروط"]
        )

        # Check entity mention or context carryover
        entity = None
        if any(w in lower for w in ["دم", "صورة الدم", "blood count", "cbc"]):
            entity = "CBC"
        else:
            for code in [
                "tsh",
                "lipid",
                "lft",
                "kft",
                "hba1c",
                "fbs",
                "vitd",
                "vitamin d",
                "فيتامين د",
                "ferritin",
                "urine",
            ]:
                if code in lower:
                    if code in ("vitd", "vitamin d", "فيتامين د"):
                        entity = "VITD"
                    else:
                        entity = code.upper()
                    break
        if not entity and context_summary and context_summary.get("selected_test_code"):
            entity = context_summary["selected_test_code"]

        is_package_selected = bool(context_summary and context_summary.get("selected_package_id"))
        if is_package_selected and not entity:
            if has_catalog_aspect or any(
                w in lower for w in ["include", "يتضمن", "تشمل", "مكونات"]
            ):
                return RequestPlan(
                    primary_intent=AgentIntent.PACKAGE_DETAILS,
                    requested_information=["price", "tests"],
                    requires_structured_data=True,
                    language=lang,
                )

        if has_catalog_aspect and has_rag_aspect:
            return RequestPlan(
                primary_intent=AgentIntent.TEST_DETAILS,
                requested_information=["definition", "price", "preparation"],
                entities={"test_query": entity or "TSH"},
                requires_structured_data=True,
                requires_rag=True,
                language=lang,
            )

        if has_rag_aspect:
            return RequestPlan(
                primary_intent=AgentIntent.PREPARATION,
                requested_information=["preparation"],
                entities={"test_query": entity},
                requires_rag=True,
                language=lang,
            )

        if has_catalog_aspect or entity:
            sub_intent = AgentIntent.TEST_DETAILS
            aspect_count = sum(
                [
                    any(w in lower for w in ["turnaround", "ready", "تظهر", "وقت"]),
                    any(w in lower for w in ["sample", "عينة"]),
                    any(w in lower for w in ["price", "cost", "بكام", "سعر", "تمن"]),
                    any(
                        w in lower
                        for w in [
                            "what does",
                            "what is",
                            "عبارة عن إيه",
                            "ما هو",
                            "measure",
                            "بيقيس",
                        ]
                    ),
                ]
            )
            if aspect_count <= 1:
                if any(w in lower for w in ["turnaround", "ready", "تظهر", "وقت"]):
                    sub_intent = AgentIntent.RESULT_TURNAROUND
                elif any(w in lower for w in ["sample", "عينة"]):
                    sub_intent = AgentIntent.SAMPLE_TYPE
                elif any(w in lower for w in ["price", "cost", "بكام", "سعر", "تمن"]):
                    sub_intent = AgentIntent.TEST_PRICE
                elif any(
                    w in lower
                    for w in ["what does", "what is", "عبارة عن إيه", "ما هو", "measure", "بيقيس"]
                ):
                    sub_intent = AgentIntent.TEST_DEFINITION

            return RequestPlan(
                primary_intent=sub_intent,
                requested_information=[sub_intent.value],
                entities={"test_query": entity or "CBC"},
                requires_structured_data=True,
                language=lang,
            )

        # General conversation
        if any(
            w in lower
            for w in [
                "hi",
                "hello",
                "thanks",
                "thank you",
                "شكرا",
                "أهلا",
                "مرحبا",
                "good morning",
                "صباح الخير",
                "help me",
            ]
        ):
            return RequestPlan(
                primary_intent=AgentIntent.GENERAL_CONVERSATION,
                language=lang,
            )

        return RequestPlan(
            primary_intent=AgentIntent.UNKNOWN_AMBIGUOUS,
            language=lang,
        )

    def generate_clarification(
        self,
        target: str | None,
        reason: str | None,
        options: list[str] | None = None,
        language: str = "en",
    ) -> str:
        self.calls.append(
            {
                "method": "generate_clarification",
                "target": target,
                "reason": reason,
                "options": options,
                "language": language,
            }
        )
        if self.canned_clarification is not None:
            return self.canned_clarification

        if language == "ar":
            if options:
                opts = "، ".join(options)
                return f"لدينا أكثر من تحليل متاح ({opts}). هل تقصد تحليل TSH الفردي أم باقة الحيوية الكاملة؟"
            return "هل يمكنك توضيح التحليل المطلوب بالتحديد لمساعدتك بشكل أفضل؟"

        if options:
            opts = ", ".join(options)
            return f"We offer multiple thyroid testing options ({opts}). Did you mean the single TSH test or the full Vitality & Wellness Panel?"
        return "Could you please specify which test or service you are interested in?"

    def compose_response(
        self,
        evidence_bundle: dict[str, Any],
    ) -> ResponseDraft:
        self.calls.append({"method": "compose_response", "evidence": evidence_bundle})
        if self.composition_handler is not None:
            return self.composition_handler(evidence_bundle)
        if self.canned_composition is not None:
            return self.canned_composition

        goal = evidence_bundle.get("response_goal", ResponseGoal.ANSWER.value)
        lang = evidence_bundle.get("language", "en")

        # Safety response
        if goal == ResponseGoal.SAFE_BOUNDARY.value:
            if lang == "ar":
                text = (
                    "في مختبرات ميدي لاب تخصصنا هو تقديم الخدمات المخبرية والفحوصات بدقة عالية. "
                    "لا يمكننا تقديم تشخيص طبي أو علاج أو وصف أدوية أو تفسير النتائج سريرياً. "
                    "يرجى استشارة طبيب مختص أو دكتور معالج لتقييم حالتك الصحية وتحديد العلاج."
                )
            else:
                text = (
                    "MediLab provides diagnostic laboratory testing and operational guidance. "
                    "We cannot diagnose conditions, prescribe medications, or interpret clinical results. "
                    "In an emergency or severe symptoms, please seek immediate emergency care at the nearest hospital. "
                    "Please consult a qualified healthcare professional, doctor, or physician regarding medical decisions."
                )
            return ResponseDraft(text=text, response_goal=ResponseGoal.SAFE_BOUNDARY)

        # Action boundary response (Phase 4 placeholder)
        if goal == ResponseGoal.ACTION_NOT_YET_EXECUTABLE.value:
            if lang == "ar":
                text = (
                    "يمكننا مساعدتك في تفاصيل التحاليل والأسعار ومواعيد الفروع. "
                    "خدمة حجز المواعيد وإلغاء الحجز قيد التفعيل حالياً وستكون متاحة في الإصدار القادم. "
                    "يرجى التواصل مع خدمة العملاء مباشرة للمساعدة في حجز أو إلغاء موعدك."
                )
            else:
                text = (
                    "I can assist you with test details, branch locations, and preparation guidelines. "
                    "Direct appointment booking service and cancellation will be activated in our upcoming release. "
                    "Please contact our customer service desk directly."
                )
            return ResponseDraft(text=text, response_goal=ResponseGoal.ACTION_NOT_YET_EXECUTABLE)

        # Controlled error / Clarification
        if goal == ResponseGoal.CLARIFY.value:
            question = evidence_bundle.get("clarification_question", "How can I help you?")
            return ResponseDraft(text=question, response_goal=ResponseGoal.CLARIFY)

        # General conversation
        if (
            goal == ResponseGoal.ANSWER.value
            and evidence_bundle.get("intent") == AgentIntent.GENERAL_CONVERSATION.value
        ):
            if lang == "ar":
                text = "أهلاً بك في معمل ميدي لاب! يسعدنا مساعدتك اليوم في الاستفسار عن التحاليل الطبية والباقات ومواعيد فروعنا."
            else:
                text = "Hello! Welcome to MediLab. How can I help you with our laboratory tests, packages, and branches today?"
            return ResponseDraft(text=text, response_goal=ResponseGoal.ANSWER)

        # Customer history
        cust_hist = evidence_bundle.get("customer_history")
        if cust_hist and cust_hist.get("bookings"):
            b = cust_hist["bookings"][0]
            items = ", ".join(b.get("items", []))
            ref = b.get("booking_reference", "")
            status = b.get("status", "")
            date_str = b.get("scheduled_date", "")
            if lang == "ar":
                text = f"آخر حجز مسجل لك برقم {ref} بتاريخ {date_str} وحالته {status} ويتضمن فحص تحليل: {items}."
            else:
                text = f"Your most recent booking ({ref}) is scheduled on {date_str} (Status: {status}) for booked test: {items}."
            return ResponseDraft(text=text, response_goal=ResponseGoal.ANSWER)
        elif evidence_bundle.get("intent") == AgentIntent.CUSTOMER_HISTORY.value:
            if lang == "ar":
                text = "يرجى تسجيل الدخول أو إثبات هويتك برقم هاتفك المسجل للاطلاع على سجل حجوزاتك السابقة."
            else:
                text = "You are not logged in. Please identify yourself with your phone number to access your previous booking history."
            return ResponseDraft(text=text, response_goal=ResponseGoal.ANSWER)

        # Unknown / out of domain queries
        if evidence_bundle.get("intent") == AgentIntent.UNKNOWN_AMBIGUOUS.value:
            if lang == "ar":
                text = "أهلاً بك في معمل ميدي لاب للتحاليل الطبية. نعتذر، فنحن معمل تحاليل طبية ولا يمكننا تقديم خدمات خارج نطاق الفحوصات المخبرية."
            else:
                text = "Welcome to MediLab. As a specialized clinical diagnostic medical laboratory, we cannot help with external services outside laboratory testing."
            return ResponseDraft(text=text, response_goal=ResponseGoal.NO_KNOWLEDGE)

        # Structured facts (SQL) and/or RAG context
        structured = evidence_bundle.get("structured_facts") or {}
        rag = evidence_bundle.get("rag_context") or []

        parts: list[str] = []
        if "test" in structured:
            t = structured["test"]
            name = t.get("name", "")
            desc = t.get("description", "")
            price = t.get("price", "")
            sample = t.get("sample_type", "")
            turnaround = t.get("turnaround", "")
            if lang == "ar":
                parts.append(
                    f"تحليل {name}: {desc} سعره {price} جنيه مصري، العينة المطلوبة: {sample}، ومدة ظهور النتيجة: {turnaround}."
                )
            else:
                parts.append(
                    f"{name} ({desc}) is priced at {price} EGP. It requires {sample}, with results ready in {turnaround}."
                )

        if "package" in structured:
            pkg = structured["package"]
            name = pkg.get("name", "")
            desc = pkg.get("description", "")
            price = pkg.get("price", "")
            tests = ", ".join(pkg.get("tests", []))
            if lang == "ar":
                parts.append(f"باقة {name}: {desc} بسعر {price} جنيه وتتضمن: {tests}.")
            else:
                parts.append(f"{name}: {desc} for {price} EGP, including tests: {tests}.")

        if "packages" in structured:
            for pkg in structured["packages"]:
                name = pkg.get("name", "")
                desc = pkg.get("description", "")
                price = pkg.get("price", "")
                if lang == "ar":
                    parts.append(f"باقة {name}: {desc} بسعر {price} جنيه.")
                else:
                    parts.append(f"Package {name}: {desc} ({price}).")

        if "branches" in structured:
            branches = structured["branches"]
            b_names = [f"{b.get('name')} ({b.get('phone')})" for b in branches]
            if lang == "ar":
                parts.append(
                    f"فروعنا المتاحة في المعادي ومدينة نصر ووسط البلد: {', '.join(b_names)}."
                )
            else:
                parts.append(f"Our branches in Downtown, Nasr City, Maadi: {', '.join(b_names)}.")

        if rag:
            rag_text = "\n".join([chunk.get("content", "") for chunk in rag[:2]])
            if lang == "ar":
                parts.append(f"شروط التحضير والسياسات: صيام {rag_text}")
            else:
                parts.append(f"Preparation & Policy instructions (fasting): {rag_text}")

        if not parts:
            if lang == "ar":
                return ResponseDraft(
                    text="عذراً، لم أجد معلومات مطابقة في دليل التحاليل الحالي. هل تود البحث عن تحليل آخر؟",
                    response_goal=ResponseGoal.NO_KNOWLEDGE,
                )
            return ResponseDraft(
                text="I could not find matching information in our current catalog. Would you like to search for another test?",
                response_goal=ResponseGoal.NO_KNOWLEDGE,
            )

        return ResponseDraft(text=" ".join(parts), response_goal=ResponseGoal.ANSWER)

    def validate_response(
        self,
        draft: str,
        evidence_bundle: dict[str, Any],
    ) -> ValidationOutcome:
        self.calls.append({"method": "validate_response", "draft": draft})
        if self.canned_validation is not None:
            return self.canned_validation

        # Check for ungrounded booking confirmations
        lower = draft.lower()
        if any(
            w in lower for w in ["your booking is confirmed", "تم تأكيد حجزك"]
        ) and not evidence_bundle.get("action_result"):
            return ValidationOutcome(
                is_valid=False,
                reasons=["Response claims confirmed booking without committed action result."],
                repaired_text="I cannot confirm bookings at this time. Please contact our support team.",
            )

        # Check for clinical diagnosis claims
        if any(w in lower for w in ["you have diabetes", "أنت مصاب بالسكري", "نوصي بتناول دواء"]):
            return ValidationOutcome(
                is_valid=False,
                reasons=[
                    "Response contains prohibited medical diagnosis or medication prescription."
                ],
                repaired_text="Please consult a doctor for medical diagnosis.",
            )

        return ValidationOutcome(is_valid=True)
