import os
from contextlib import contextmanager
from functools import lru_cache
import tempfile

import mysql.connector


@lru_cache(maxsize=1)
def ca_certificate():
    pem = os.getenv("DB_SSL_CA_PEM")
    if pem:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as certificate:
            certificate.write(pem)
            return certificate.name
    return os.getenv("DB_SSL_CA", "/etc/ssl/certs/ca-certificates.crt")


@contextmanager
def session():
    """One short MySQL transaction per API request."""
    tls_options = {}
    if os.getenv("DB_SSL", "false").lower() == "true":
        tls_options = {"ssl_disabled": False, "ssl_verify_cert": True, "ssl_verify_identity": True,
                       "ssl_ca": ca_certificate()}
    if os.getenv("APP_ENV") == "production" and not tls_options:
        raise RuntimeError("Production requires DB_SSL=true for the hosted MySQL connection.")
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "court_case_tracker"),
        connection_timeout=5,
        **tls_options,
    )
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def all_rows(connection, sql, params=()):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()


def one_row(connection, sql, params=()):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        cursor.close()


def insert_row(connection, sql, params):
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        return cursor.lastrowid
    finally:
        cursor.close()
