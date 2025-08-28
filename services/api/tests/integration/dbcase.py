import os, unittest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

TEST_DB_URL = os.getenv("TEST_DB_URL", "postgresql+psycopg://postgres:postgres@postgres-test:5432/game_test")

class DBTestCase(unittest.TestCase):
    engine = None
    connection = None
    trans = None
    session = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = create_engine(TEST_DB_URL, future=True)
        from app import db as app_db
        app_db.metadata.create_all(bind=cls.engine)
        cls.connection = cls.engine.connect()
        cls.trans = cls.connection.begin()
        cls.Session = sessionmaker(bind=cls.connection, future=True)
        cls.session = cls.Session()

        @event.listens_for(cls.session, "after_transaction_end")
        def restart_savepoint(session, transaction):
            if transaction.nested and not transaction._parent:
                try:
                    session.begin_nested()
                except Exception:
                    pass

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.session:
                cls.session.close()
            if cls.trans:
                cls.trans.rollback()
            if cls.connection:
                cls.connection.close()
            if cls.engine:
                cls.engine.dispose()
        finally:
            super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.session.begin_nested()

    def tearDown(self):
        super().tearDown()
