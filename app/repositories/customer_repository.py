"""Repository for Customer entities."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models.customer import Customer


class CustomerRepository:
    """Data access repository for customer profiles."""

    def get_by_id(self, customer_id: int) -> Customer | None:
        """Fetch customer by ID."""
        stmt = select(Customer).where(Customer.id == customer_id)
        return db.session.execute(stmt).scalar_one_or_none()

    def get_by_phone(self, phone: str) -> Customer | None:
        """Fetch customer by normalized unique phone number."""
        normalized_phone = phone.strip()
        stmt = select(Customer).where(Customer.phone == normalized_phone)
        return db.session.execute(stmt).scalar_one_or_none()

    def get_or_create(self, name: str, phone: str, email: str | None = None) -> Customer:
        """Unambiguously resolve or create customer record based on unique phone."""
        normalized_phone = phone.strip()
        customer = self.get_by_phone(normalized_phone)
        if customer is None:
            customer = Customer(
                name=name.strip(),
                phone=normalized_phone,
                email=email.strip() if email else None,
            )
            db.session.add(customer)
            db.session.flush()
        else:
            # Update name or email if provided
            if name and customer.name != name.strip():
                customer.name = name.strip()
            if email and customer.email != email.strip():
                customer.email = email.strip()
            db.session.flush()

        return customer
