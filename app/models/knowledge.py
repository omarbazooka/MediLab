"""KnowledgeDocument and KnowledgeChunk models for preparation policies and RAG storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSON_VARIANT, TSVECTOR_VARIANT, TimestampMixin


class KnowledgeDocument(TimestampMixin, db.Model):
    """Authoritative non-clinical laboratory policy, guideline, or instruction document."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "index_status IN ('PENDING', 'INDEXING', 'READY', 'FAILED')",
            name="ck_knowledge_docs_index_status",
        ),
        Index("ix_knowledge_docs_category_active", "category", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    index_status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        index=True,
        nullable=False,
    )
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index",
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeDocument id={self.id} title='{self.title}' "
            f"category='{self.category}' status='{self.index_status}'>"
        )


class KnowledgeChunk(TimestampMixin, db.Model):
    """Discrete text chunk from a KnowledgeDocument with vector and FTS representation."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_chunk_index"),
        Index(
            "ix_knowledge_chunks_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Phase 2 runtime embeddings use jina-embeddings-v3 with explicit 384-dim output.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON_VARIANT,
        default=dict,
        nullable=False,
    )
    search_vector: Mapped[Any] = mapped_column(TSVECTOR_VARIANT, nullable=True)

    document: Mapped[KnowledgeDocument] = relationship("KnowledgeDocument", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<KnowledgeChunk id={self.id} doc_id={self.document_id} chunk={self.chunk_index}>"
