"""Database connection and session management"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from finquarium_proof.models.db import Base
from finquarium_proof.config import settings

logger = logging.getLogger(__name__)

class Database:
    """Database connection manager"""
    def __init__(self):
        self._engine = None
        self._SessionLocal = None

    def init(self) -> None:
        """Initialize database connection and create tables"""
        try:
            self._engine = create_engine(settings.POSTGRES_URL)
            Base.metadata.create_all(self._engine)
            self._SessionLocal = sessionmaker(bind=self._engine)
            logger.info("Database initialized successfully")
        except SQLAlchemyError as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations"""
        if not self._SessionLocal:
            raise RuntimeError("Database not initialized. Call init() first.")

        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self) -> Session:
        """Get a new database session"""
        if not self._SessionLocal:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._SessionLocal()

# Global database instance
db = Database()