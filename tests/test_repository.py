"""Tests for the JSON book repository."""

import json
import tempfile
import unittest
from pathlib import Path

from library.models import Book
from library.repository import BookRepository


def book_payload(**overrides: object) -> dict[str, object]:
    """Build a valid JSON entry, overriding only the fields a test needs."""
    entry: dict[str, object] = {
        "id": "B001",
        "title": "Clean Code",
        "author": "Robert C. Martin",
        "isbn": "9780132350884",
        "category": "Software Engineering",
        "total_copies": 3,
        "available_copies": 2,
    }
    entry.update(overrides)
    return entry


class BookRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.path = Path(temp_dir.name) / "books.json"

    def write(self, payload: object) -> None:
        content = payload if isinstance(payload, str) else json.dumps(payload)
        self.path.write_text(content, encoding="utf-8")

    def test_loads_books_from_json(self) -> None:
        self.write([book_payload()])

        books = BookRepository(self.path).load()

        self.assertEqual(len(books), 1)
        self.assertIsInstance(books[0], Book)
        self.assertEqual(books[0].title, "Clean Code")

    def test_missing_catalogue_is_empty(self) -> None:
        self.assertEqual(BookRepository(self.path).load(), [])

    def test_rejects_invalid_json(self) -> None:
        self.write("{not json")

        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            BookRepository(self.path).load()

    def test_rejects_payload_that_is_not_a_list(self) -> None:
        self.write({"books": []})

        with self.assertRaisesRegex(ValueError, "must contain a JSON list"):
            BookRepository(self.path).load()

    def test_rejects_entry_that_is_not_an_object(self) -> None:
        self.write([book_payload(), 42])

        with self.assertRaisesRegex(ValueError, "entry 2.*must be a JSON object"):
            BookRepository(self.path).load()

    def test_rejects_entry_with_missing_or_unexpected_fields(self) -> None:
        missing_isbn = book_payload()
        del missing_isbn["isbn"]

        for entry in (missing_isbn, book_payload(shelf="A1")):
            with self.subTest(entry=entry):
                self.write([entry])
                with self.assertRaisesRegex(ValueError, "does not match the book schema"):
                    BookRepository(self.path).load()

    def test_rejects_entry_with_invalid_book_data(self) -> None:
        self.write([book_payload(total_copies=1, available_copies=5)])

        with self.assertRaisesRegex(ValueError, "entry 1.*is invalid"):
            BookRepository(self.path).load()

    def test_saved_catalogue_can_be_loaded_again(self) -> None:
        repository = BookRepository(self.path)
        book = Book(**book_payload())  # type: ignore[arg-type]

        repository.save([book])

        self.assertEqual(repository.load(), [book])

    def test_save_creates_missing_directories(self) -> None:
        path = Path(self.path.parent, "nested", "books.json")
        book = Book(**book_payload())  # type: ignore[arg-type]

        BookRepository(path).save([book])

        self.assertTrue(path.exists())
        self.assertEqual(BookRepository(path).load(), [book])


if __name__ == "__main__":
    unittest.main()
