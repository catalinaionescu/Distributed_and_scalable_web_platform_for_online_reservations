import os
from mysql.connector import pooling
from contextlib import contextmanager
from config import Config

db_pool = None

def get_db_pool():
    global db_pool
    if db_pool is None:
        print(f"Proces [{os.getpid()}] creează pool pentru DB locală...")
        db_pool = pooling.MySQLConnectionPool(
            pool_name=f"local_db_{os.getpid()}", 
            pool_size=32, 
            **Config.DB_CONFIG
        )
    return db_pool

@contextmanager
def get_db_connection():
    """Obține o conexiune de la pool-ul local pentru CITIRE și SCRIERE."""
    cnx = None
    try:
        cnx = get_db_pool().get_connection()
        yield cnx
    finally:
        if cnx: cnx.close()

@contextmanager
def get_db_cursor(cnx, dictionary=True):
    cursor = None
    try:
        cursor = cnx.cursor(dictionary=dictionary)
        yield cursor
    finally:
        if cursor: cursor.close()