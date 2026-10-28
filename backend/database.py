"""Small PostgreSQL adapter matching the SQLite connection surface used by OpsPilot."""

from __future__ import annotations

import psycopg
from psycopg import pq


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            key = tuple(self)[key]
        return super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(zip(names, values))


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type:
            self.rollback()
        else:
            self.commit()
        return False

    def execute(self, statement, parameters=()):
        statement = statement.replace("?", "%s")
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            statement = "BEGIN"
        return self.connection.execute(statement, parameters)

    def executemany(self, statement, parameters):
        statement = statement.replace("?", "%s")
        return self.connection.cursor().executemany(statement, parameters)

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    @property
    def in_transaction(self):
        return self.connection.info.transaction_status != pq.TransactionStatus.IDLE

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def connect(url):
    return Connection(psycopg.connect(url, connect_timeout=5, row_factory=row_factory))
