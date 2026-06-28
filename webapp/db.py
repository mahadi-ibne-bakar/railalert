import os

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]


def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
