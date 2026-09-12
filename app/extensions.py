"""Extensions module for MediLab AI.

Centralized registry for Flask extensions. Extension singletons are defined here
unbound, and bound to the application instance inside the application factory
using the `init_app()` method.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Relational persistence extension (PostgreSQL + pgvector)
db: SQLAlchemy = SQLAlchemy()

# Database migration management extension (Alembic)
migrate: Migrate = Migrate()
