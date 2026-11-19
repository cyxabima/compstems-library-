"""Tests for the command-line book list."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from library.cli import (
    EMPTY_CATALOGUE_MESSAGE,
    NO_BOOKS_FOUND_MESSAGE,
    format_books,
    run,
)
from library.models import Book

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_book(**overrides: object) -> Book:
    fields: dict[str, object] = {
        "id": "B001",
        "title": "Alpha",
        "author": "Author",
        "isbn": "9780000000001",
        "category": "General",
        "total_copies": 2,
        "available_copies": 1,
    }
    fields.update(overrides)
    return Book(**fields)  # type: ignore[arg-type]


def catalogue_entry(**overrides: object) -> dict[str, object]:
    book = make_book(**overrides)
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "category": book.category,
        "total_copies": book.total_copies,
        "available_copies": book.available_copies,
    }


class FormatBooksTests(unittest.TestCase):
    def test_renders_every_catalogue_field_in_order(self) -> None:
        output = format_books([make_book()])
        lines = output.splitlines()

        self.assertEqual(
            lines[0].split(),
            ["ID", "Title", "Author", "ISBN", "Category", "Available/Total"],
        )
        self.assertEqual(
            lines[2].split(),
            ["B001", "Alpha", "Author", "9780000000001", "General", "1/2"],
        )

    def test_renders_one_row_per_book(self) -> None:
        books = [
            make_book(id="B001", title="Alpha"),
            make_book(id="B002", title="Beta"),
        ]

        lines = format_books(books).splitlines()

        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[2].startswith("B001"))
        self.assertTrue(lines[3].startswith("B002"))

    def test_shows_available_over_total_copies(self) -> None:
        book = make_book(total_copies=5, available_copies=0)

        self.assertIn("0/5", format_books([book]))

    def test_empty_catalogue_has_a_friendly_message(self) -> None:
        self.assertEqual(format_books([]), EMPTY_CATALOGUE_MESSAGE)


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.path = Path(temp_dir.name) / "books.json"

    def write(self, payload: object) -> None:
        content = payload if isinstance(payload, str) else json.dumps(payload)
        self.path.write_text(content, encoding="utf-8")

    def capture(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = run(argv)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_lists_books_sorted_by_title(self) -> None:
        self.write(
            [
                catalogue_entry(id="B002", title="Beta"),
                catalogue_entry(id="B001", title="alpha"),
            ]
        )

        status, stdout, stderr = self.capture(["--data", str(self.path)])
        rows = [line.split() for line in stdout.splitlines()[2:]]

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual([row[0] for row in rows], ["B001", "B002"])

    def test_search_shows_only_matching_books(self) -> None:
        self.write(
            [
                catalogue_entry(
                    id="B001",
                    title="Clean Code",
                    author="Robert C. Martin",
                ),
                catalogue_entry(
                    id="B002",
                    title="Sapiens",
                    author="Yuval Noah Harari",
                ),
            ]
        )

        status, stdout, stderr = self.capture(
            ["--data", str(self.path), "--search", "ROBERT"]
        )
        rows = [line.split() for line in stdout.splitlines()[2:]]

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual([row[0] for row in rows], ["B001"])

    def test_search_without_matches_shows_no_books_found(self) -> None:
        self.write([catalogue_entry()])

        status, stdout, stderr = self.capture(
            ["--data", str(self.path), "--search", "astronomy"]
        )

        self.assertEqual(status, 0)
        self.assertEqual(stdout.strip(), NO_BOOKS_FOUND_MESSAGE)
        self.assertEqual(stderr, "")

    def test_reports_invalid_catalogue_without_a_traceback(self) -> None:
        self.write("{not json")

        status, stdout, stderr = self.capture(["--data", str(self.path)])

        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.startswith("Error:"))


class MainScriptTests(unittest.TestCase):
    def test_python_main_lists_the_sample_catalogue(self) -> None:
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Available/Total", result.stdout)
        self.assertIn("Clean Code", result.stdout)

    def test_python_main_searches_the_sample_catalogue(self) -> None:
        result = subprocess.run(
            [sys.executable, "main.py", "--search", "history"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Sapiens", result.stdout)
        self.assertNotIn("Clean Code", result.stdout)


if __name__ == "__main__":
    unittest.main()
