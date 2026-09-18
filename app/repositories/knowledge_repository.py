"""Data access repository for KnowledgeDocument and KnowledgeChunk entities."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.rag.types import LexicalCandidate, SemanticCandidate


class KnowledgeRepository:
    """Repository handling database access for knowledge documents, chunks, and hybrid retrieval."""

    def get_document_by_id(self, document_id: int) -> KnowledgeDocument | None:
        """Fetch a single knowledge document by primary key ID."""
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .options(selectinload(KnowledgeDocument.chunks))
        )
        return db.session.execute(stmt).scalar_one_or_none()

    def list_documents(
        self,
        category: str | None = None,
        active: bool | None = None,
        index_status: str | None = None,
    ) -> list[KnowledgeDocument]:
        """List knowledge documents with optional metadata and status filters."""
        stmt = select(KnowledgeDocument).options(selectinload(KnowledgeDocument.chunks))

        if category is not None:
            stmt = stmt.where(KnowledgeDocument.category == category.strip())
        if active is not None:
            stmt = stmt.where(KnowledgeDocument.active.is_(active))
        if index_status is not None:
            stmt = stmt.where(KnowledgeDocument.index_status == index_status.strip().upper())

        stmt = stmt.order_by(KnowledgeDocument.id.asc())
        return list(db.session.execute(stmt).scalars().all())

    def create_document(
        self,
        title: str,
        category: str,
        content: str,
        active: bool = True,
        version: int = 1,
        index_status: str = "PENDING",
    ) -> KnowledgeDocument:
        """Persist a new knowledge document record in PENDING status."""
        doc = KnowledgeDocument(
            title=title.strip(),
            category=category.strip(),
            content=content.strip(),
            active=active,
            version=version,
            index_status=index_status,
        )
        db.session.add(doc)
        db.session.flush()
        return doc

    def update_document(
        self,
        document: KnowledgeDocument,
        title: str | None = None,
        category: str | None = None,
        content: str | None = None,
        active: bool | None = None,
    ) -> KnowledgeDocument:
        """Update mutable fields on an existing knowledge document."""
        if title is not None:
            document.title = title.strip()
        if category is not None:
            document.category = category.strip()
        if content is not None:
            document.content = content.strip()
        if active is not None:
            document.active = active
        db.session.flush()
        return document

    def delete_document(self, document: KnowledgeDocument) -> None:
        """Delete a knowledge document and cascade-delete its chunks."""
        db.session.delete(document)
        db.session.flush()

    def set_document_status(
        self,
        document_id: int,
        status: str,
        error: str | None = None,
        indexed_at: datetime | None = None,
    ) -> None:
        """Update indexing lifecycle status and error information."""
        doc = self.get_document_by_id(document_id)
        if doc is None:
            return

        doc.index_status = status
        doc.index_error = error
        if indexed_at is not None:
            doc.last_indexed_at = indexed_at
        elif status == "READY":
            doc.last_indexed_at = datetime.now(UTC)
        db.session.flush()

    def get_chunks_by_document(self, document_id: int) -> list[KnowledgeChunk]:
        """Fetch all chunks for a document ordered by chunk_index."""
        stmt = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
        return list(db.session.execute(stmt).scalars().all())

    def replace_document_chunks(
        self,
        document_id: int,
        chunk_specs: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> list[KnowledgeChunk]:
        """Atomically replace all chunks for a document within the active transaction."""
        existing = self.get_chunks_by_document(document_id)
        for chunk in existing:
            db.session.delete(chunk)
        db.session.flush()

        new_chunks: list[KnowledgeChunk] = []
        for idx, spec in enumerate(chunk_specs):
            embedding = embeddings[idx] if idx < len(embeddings) else None
            chunk = KnowledgeChunk(
                document_id=document_id,
                chunk_index=spec["chunk_index"],
                content=spec["content"],
                embedding=embedding,
                metadata_=spec.get("metadata", {}),
            )
            db.session.add(chunk)
            new_chunks.append(chunk)

        db.session.flush()
        return new_chunks

    @staticmethod
    def _is_postgresql() -> bool:
        try:
            return db.engine.dialect.name == "postgresql"
        except Exception:
            return False

    @staticmethod
    def _chunk_matches_current_version(
        chunk: KnowledgeChunk,
        document: KnowledgeDocument,
    ) -> bool:
        """Return True only when chunk metadata belongs to the document's current version."""
        metadata = chunk.metadata_ or {}
        chunk_version = metadata.get("document_version")
        try:
            return int(chunk_version) == document.version
        except (TypeError, ValueError):
            return False

    def search_semantic(
        self,
        query_embedding: list[float],
        top_k: int = 8,
        category: str | None = None,
        document_ids: list[int] | None = None,
    ) -> list[SemanticCandidate]:
        """Retrieve top semantic candidates using pgvector cosine distance (<=>).

        Only returns chunks from active READY documents whose chunk metadata matches
        the current KnowledgeDocument.version.
        """
        candidate_window = max(top_k * 4, top_k)

        if self._is_postgresql():
            distance_expr = KnowledgeChunk.embedding.cosine_distance(query_embedding).label(
                "distance"
            )
            stmt = (
                select(KnowledgeChunk, KnowledgeDocument, distance_expr)
                .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(
                    KnowledgeDocument.active.is_(True),
                    KnowledgeDocument.index_status == "READY",
                    KnowledgeChunk.embedding.is_not(None),
                )
            )

            if category:
                stmt = stmt.where(KnowledgeDocument.category == category.strip())
            if document_ids:
                stmt = stmt.where(KnowledgeDocument.id.in_(document_ids))

            stmt = stmt.order_by(distance_expr.asc(), KnowledgeChunk.id.asc()).limit(
                candidate_window
            )
            rows = db.session.execute(stmt).all()

            candidates: list[SemanticCandidate] = []
            for chunk, doc, dist in rows:
                if not self._chunk_matches_current_version(chunk, doc):
                    continue
                candidates.append(
                    SemanticCandidate(
                        chunk_id=chunk.id,
                        document_id=doc.id,
                        document_title=doc.title,
                        document_category=doc.category,
                        document_version=doc.version,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        cosine_distance=float(dist) if dist is not None else 1.0,
                        semantic_rank=len(candidates) + 1,
                        chunk_metadata=chunk.metadata_ or {},
                    )
                )
                if len(candidates) >= top_k:
                    break
            return candidates

        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.active.is_(True),
                KnowledgeDocument.index_status == "READY",
                KnowledgeChunk.embedding.is_not(None),
            )
        )
        if category:
            stmt = stmt.where(KnowledgeDocument.category == category.strip())
        if document_ids:
            stmt = stmt.where(KnowledgeDocument.id.in_(document_ids))

        rows = db.session.execute(stmt).all()
        scored: list[tuple[KnowledgeChunk, KnowledgeDocument, float]] = []
        for chunk, doc in rows:
            if not self._chunk_matches_current_version(chunk, doc):
                continue
            vec = chunk.embedding or []
            if len(vec) == len(query_embedding):
                dot = sum(a * b for a, b in zip(vec, query_embedding, strict=True))
                norm_a = math.sqrt(sum(a * a for a in vec))
                norm_b = math.sqrt(sum(b * b for b in query_embedding))
                sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
                dist = max(0.0, 1.0 - sim)
            else:
                dist = 1.0
            scored.append((chunk, doc, dist))

        scored.sort(key=lambda item: (item[2], item[0].id))
        candidates: list[SemanticCandidate] = []
        for chunk, doc, dist in scored[:top_k]:
            candidates.append(
                SemanticCandidate(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    document_title=doc.title,
                    document_category=doc.category,
                    document_version=doc.version,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    cosine_distance=dist,
                    semantic_rank=len(candidates) + 1,
                    chunk_metadata=chunk.metadata_ or {},
                )
            )
        return candidates

    def search_lexical(
        self,
        query_text: str,
        top_k: int = 8,
        category: str | None = None,
        document_ids: list[int] | None = None,
    ) -> list[LexicalCandidate]:
        """Retrieve top lexical candidates using PostgreSQL FTS.

        Only returns chunks from active READY documents whose chunk metadata matches
        the current KnowledgeDocument.version.
        """
        clean_text = query_text.strip()
        if not clean_text:
            return []

        lexical_stop_words = {
            "does",
            "do",
            "did",
            "is",
            "are",
            "was",
            "were",
            "what",
            "how",
            "why",
            "when",
            "where",
            "which",
            "who",
            "can",
            "could",
            "would",
            "should",
            "the",
            "a",
            "an",
            "and",
            "or",
            "for",
            "to",
            "in",
            "on",
            "at",
            "of",
            "from",
            "by",
            "with",
            "about",
            "provide",
            "provides",
            "medilab",
            "someone",
            "come",
            "my",
            "هل",
            "ما",
            "ماذا",
            "كيف",
            "متى",
            "أين",
            "من",
            "في",
            "على",
            "عن",
            "إلى",
            "مع",
            "معمل",
            "هو",
            "هي",
            "ده",
            "دي",
        }
        candidate_window = max(top_k * 4, top_k)

        if self._is_postgresql():
            raw_tokens = [re.sub(r"[^\w]", "", w) for w in clean_text.split()]
            tokens = [t for t in raw_tokens if len(t) > 1 and t.lower() not in lexical_stop_words]

            if not tokens:
                tokens = [t for t in raw_tokens if len(t) > 1]
                if not tokens:
                    return []

            safe_terms = " | ".join(f"'{t}'" for t in tokens)
            tsquery = func.to_tsquery("simple", safe_terms)
            rank_expr = func.ts_rank_cd(KnowledgeChunk.search_vector, tsquery).label("rank_score")

            stmt = (
                select(KnowledgeChunk, KnowledgeDocument, rank_expr)
                .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(
                    KnowledgeDocument.active.is_(True),
                    KnowledgeDocument.index_status == "READY",
                    KnowledgeChunk.search_vector.op("@@")(tsquery),
                )
            )

            if category:
                stmt = stmt.where(KnowledgeDocument.category == category.strip())
            if document_ids:
                stmt = stmt.where(KnowledgeDocument.id.in_(document_ids))

            stmt = stmt.order_by(rank_expr.desc(), KnowledgeChunk.id.asc()).limit(candidate_window)
            rows = db.session.execute(stmt).all()

            candidates: list[LexicalCandidate] = []
            for chunk, doc, score in rows:
                if not self._chunk_matches_current_version(chunk, doc):
                    continue
                candidates.append(
                    LexicalCandidate(
                        chunk_id=chunk.id,
                        document_id=doc.id,
                        document_title=doc.title,
                        document_category=doc.category,
                        document_version=doc.version,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        fts_score=float(score) if score is not None else 0.0,
                        lexical_rank=len(candidates) + 1,
                        chunk_metadata=chunk.metadata_ or {},
                    )
                )
                if len(candidates) >= top_k:
                    break
            return candidates

        raw_tokens = [re.sub(r"[^\w]", "", w).lower() for w in clean_text.split()]
        tokens = [t for t in raw_tokens if len(t) > 1 and t not in lexical_stop_words]
        if not tokens:
            tokens = [t for t in raw_tokens if len(t) > 1]
            if not tokens:
                return []
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.active.is_(True),
                KnowledgeDocument.index_status == "READY",
            )
        )
        if category:
            stmt = stmt.where(KnowledgeDocument.category == category.strip())
        if document_ids:
            stmt = stmt.where(KnowledgeDocument.id.in_(document_ids))

        rows = db.session.execute(stmt).all()
        scored_lex: list[tuple[KnowledgeChunk, KnowledgeDocument, float]] = []
        for chunk, doc in rows:
            if not self._chunk_matches_current_version(chunk, doc):
                continue
            content_lower = chunk.content.lower()
            matches = sum(1 for t in tokens if t in content_lower)
            if matches > 0:
                score = matches / max(1, len(tokens))
                scored_lex.append((chunk, doc, score))

        scored_lex.sort(key=lambda item: (-item[2], item[0].id))
        candidates: list[LexicalCandidate] = []
        for chunk, doc, score in scored_lex[:top_k]:
            candidates.append(
                LexicalCandidate(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    document_title=doc.title,
                    document_category=doc.category,
                    document_version=doc.version,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    fts_score=score,
                    lexical_rank=len(candidates) + 1,
                    chunk_metadata=chunk.metadata_ or {},
                )
            )
        return candidates
