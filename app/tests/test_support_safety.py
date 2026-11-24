"""The safety rules of tests/support.py, checked with a fake connection (no database).

They prove that the helpers refuse to run when the active database is not
`recco_test` and that the schema script's dangerous statements are never executed.
"""
import unittest
from unittest import mock

from tests import support


class FakeConnection:
    """Records every statement; `database` is what SELECT DATABASE() reports."""

    def __init__(self, database):
        self.database = database
        self.executed = []
        self._last = None

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._last = sql
        if "SELECT DATABASE()" not in sql:
            self.executed.append(sql)

    def fetchone(self):
        return {"name": self.database}

    def commit(self):
        pass


class SafetyGuardTest(unittest.TestCase):
    def test_assert_test_database_rejects_the_development_database(self):
        with self.assertRaises(support.UnsafeDatabaseError):
            support.assert_test_database(FakeConnection("recco"))
        with self.assertRaises(support.UnsafeDatabaseError):
            support.assert_test_database(FakeConnection(None))
        support.assert_test_database(FakeConnection("recco_test"))  # no error

    def test_execute_checked_does_not_run_anything_on_the_wrong_database(self):
        conn = FakeConnection("recco")
        with self.assertRaises(support.UnsafeDatabaseError):
            support.execute_checked(conn, "DELETE FROM users")
        self.assertEqual(conn.executed, [])

    def test_reset_data_and_schema_refuse_the_wrong_database(self):
        conn = FakeConnection("recco")
        with self.assertRaises(support.UnsafeDatabaseError):
            support.reset_data(conn, support.default_users())
        with self.assertRaises(support.UnsafeDatabaseError):
            support.reset_schema(conn)
        self.assertEqual(conn.executed, [])

    def test_schema_reset_skips_use_and_create_database(self):
        conn = FakeConnection("recco_test")
        support.reset_schema(conn)
        joined = "\n".join(conn.executed).upper()
        self.assertNotIn("CREATE DATABASE", joined)
        self.assertNotRegex(joined, r"(^|\n)\s*USE\s")
        self.assertEqual(sum(s.upper().startswith("DROP TABLE IF EXISTS") for s in conn.executed), 10)
        self.assertEqual(sum(s.upper().startswith("CREATE TABLE") for s in conn.executed), 10)
        self.assertEqual(len(conn.executed), 21)  # SET time_zone + 10 DROP + 10 CREATE

    def test_unexpected_schema_statements_are_not_executed(self):
        dangerous = ["DROP DATABASE recco;", "USE somewhere_else;", "TRUNCATE TABLE users;",
                     "DELETE FROM users;", "CREATE TABLE t (x INT) -- recco\n;",
                     "CREATE DATABASE IF NOT EXISTS other;"]
        for script in dangerous:
            with self.subTest(script=script):
                conn = FakeConnection("recco_test")
                with mock.patch.object(support, "_schema_sql", return_value=script):
                    with self.assertRaises(support.UnsafeDatabaseError):
                        support.reset_schema(conn)
                self.assertEqual(conn.executed, [])


if __name__ == "__main__":
    unittest.main()
