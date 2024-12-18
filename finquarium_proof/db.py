import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager
import logging

from finquarium_proof.models.db_models import Base

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.engine = None
        self.Session = None

    def init(self):
        """Initialize database connection"""
        postgres_url = os.environ.get('POSTGRES_URL')
        if not postgres_url:
            raise ValueError("POSTGRES_URL environment variable not set")

        try:
            self.engine = create_engine(postgres_url)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            logger.info("Database initialized successfully")
        except SQLAlchemyError as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    @contextmanager
    def session(self):
        """Provide a transactional scope around a series of operations"""
        if not self.Session:
            raise RuntimeError("Database not initialized. Call init() first.")

        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

db = Database()