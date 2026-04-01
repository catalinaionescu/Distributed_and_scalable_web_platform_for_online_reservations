from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from contextlib import contextmanager
from config import Config

master_engine = create_engine(Config.DB_URL_MASTER, pool_size=10, max_overflow=20)
slave_engine = create_engine(Config.DB_URL_SLAVE, pool_size=10, max_overflow=20)

@contextmanager
def get_db_master_connection():
    conn = None
    try:
        conn = master_engine.connect()
        yield conn
    finally:
        if conn:
            conn.close()

def fetch_all(engine, query, params=None):
    with engine.connect() as cnx:
        result = cnx.execute(text(query), params or {})
        return result.mappings().all()

def fetch_one(engine, query, params=None):
    with engine.connect() as cnx:
        result = cnx.execute(text(query), params or {})
        return result.mappings().first()

def execute_commit(engine, query, params=None):
    with engine.connect() as cnx:
        result = cnx.execute(text(query), params or {})
        cnx.commit()
        if result.is_insert:
            return result.inserted_primary_key[0]
        return None