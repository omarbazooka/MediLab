"""Central models registry for MediLab AI.

Imports all domain models to ensure SQLAlchemy metadata registration for Alembic migrations.
"""

from app.models.booking import Booking, BookingItem
from app.models.branch import AvailabilitySlot, Branch
from app.models.conversation import ChatMessage, ConversationSession
from app.models.customer import Customer
from app.models.home_visit import HomeVisit
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.package import Package, PackageTest
from app.models.snapshot import SearchSnapshot
from app.models.test import LabTest, TestCategory

__all__ = [
    "AvailabilitySlot",
    "Booking",
    "BookingItem",
    "Branch",
    "ChatMessage",
    "ConversationSession",
    "Customer",
    "HomeVisit",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "LabTest",
    "Package",
    "PackageTest",
    "SearchSnapshot",
    "TestCategory",
]
