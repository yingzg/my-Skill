import pytest
from unittest.mock import patch, MagicMock
from api_flow.db import Database
from api_flow.variables import RuntimeVariables


class TestDatabase:
    @patch("api_flow.db.pymysql.connect")
    def test_execute_prepare_calls_execute(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db = Database(host="localhost", user="root", password="", database="test")
        db.execute_prepare(["INSERT INTO users (name) VALUES ('test');"], RuntimeVariables())

        mock_cursor.execute.assert_called()

    @patch("api_flow.db.pymysql.connect")
    def test_execute_cleanup_calls_execute(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db = Database(host="localhost", user="root", password="", database="test")
        db.execute_cleanup(["DELETE FROM users WHERE id = 1;"])

        mock_cursor.execute.assert_called()

    @patch("api_flow.db.pymysql.connect")
    def test_close_disconnects(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db = Database(host="localhost", user="root", password="", database="test")
        db.execute_cleanup(["DELETE FROM users WHERE id = 1;"])
        db.close()

        mock_conn.close.assert_called()

    @patch("api_flow.db.pymysql.connect")
    def test_consecutive_errors_tracked(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        import pymysql
        retryable_err = pymysql.OperationalError(1213, "Deadlock")
        mock_cursor.execute.side_effect = retryable_err
        mock_connect.return_value = mock_conn

        db = Database(host="localhost", user="root", password="", database="test")

        with pytest.raises(Exception):
            db.execute_prepare(["INSERT INTO t VALUES (1);"], RuntimeVariables())

        assert db.consecutive_errors == 1

    @patch("api_flow.db.pymysql.connect")
    def test_context_manager(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        with Database(host="localhost", user="root", password="", database="test") as db:
            db.execute_cleanup(["DELETE FROM users WHERE id = 1;"])

        mock_conn.close.assert_called()
