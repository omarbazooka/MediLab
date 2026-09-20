"""Unit tests for combined_read_node multi-source evidence gathering."""

from __future__ import annotations

from unittest.mock import patch

from flask import Flask

from app.agent.nodes.combined_read_node import combined_read_node
from app.agent.state import create_initial_state
from app.rag.types import RAGResult, RetrievedChunk


def test_combined_read_node_executes_both_sources(app: Flask) -> None:
    """Ensure combined_read_node queries SQL for catalog facts and RAG for preparation."""
    mock_rag_result = RAGResult(
        original_query="What is TSH, how much is it, and do I need to fast?",
        rewritten_query="TSH test preparation fasting guidelines",
        outcome="GOOD",
        attempt_count=1,
        final_chunks=[
            RetrievedChunk(
                chunk_id=1,
                document_id=1,
                document_title="Test Preparation Guide",
                document_category="Preparation",
                document_version=1,
                chunk_index=0,
                content="TSH does not strictly require fasting, but morning collection is advised.",
                rrf_score=0.92,
                chunk_metadata={
                    "source_file": "01_Patient_Test_Preparation.pdf",
                    "page_start": 3,
                    "section_title": "Thyroid Hormone Tests",
                },
            )
        ],
        sources=["01_Patient_Test_Preparation.pdf"],
        context=None,
    )

    from decimal import Decimal

    from app.extensions import db
    from app.models.test import LabTest, TestCategory

    with (
        app.app_context(),
        patch("app.agent.nodes.rag_node.RAGService.retrieve", return_value=mock_rag_result),
    ):
        db.create_all()
        cat = TestCategory(name="Endocrinology", slug="endocrinology", active=True)
        db.session.add(cat)
        db.session.flush()
        tsh = LabTest(
            code="TSH",
            name="Thyroid Stimulating Hormone (TSH)",
            category_id=cat.id,
            short_description="Measures thyroid-stimulating hormone.",
            sample_type="Serum",
            price=Decimal("220.00"),
            result_turnaround_text="24 Hours",
            active=True,
        )
        db.session.add(tsh)
        db.session.commit()

        state = create_initial_state(
            "session-comb-1", "What is TSH, how much is it, and do I need to fast?"
        )
        state["entities"] = {"test_query": "TSH"}

        update = combined_read_node(state)

        assert update["structured_result"] is not None
        assert "combined_read_node" in update["route_trace"]
        assert update["rag_result"] is not None
        assert update["rag_result"]["outcome"] == "GOOD"
        assert len(update["rag_result"]["chunks"]) == 1
        assert "TSH" in update["rag_result"]["chunks"][0]["content"]
