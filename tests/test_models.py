"""Tests for the Book domain model."""

import unittest

from library.models import Book


def make_book(**overrides: object) -> Book:
    """Build a valid book, overriding only the fields a test needs."""
    fields: dict[str, object] = {
        "id": "B001",
        "title": "Clean Code",
        "author": "Robert C. Martin",
        "isbn": "9780132350884",
        "category": "Software Engineering",
        "total_copies": 3,
        "available_copies": 2,
    }
    fields.update(overrides)
    return Book(**fields)  # type: ignore[arg-type]


class BookTests(unittest.TestCase):
    def test_book_exposes_catalogue_fields(self) -> None:
        book = make_book()

        self.assertEqual(book.id, "B001")
        self.assertEqual(book.title, "Clean Code")
        self.assertEqual(book.author, "Robert C. Martin")
        self.assertEqual(book.isbn, "9780132350884")
        self.assertEqual(book.category, "Software Engineering")
        self.assertEqual(book.total_copies, 3)
        self.assertEqual(book.available_copies, 2)

    def test_book_is_available_when_a_copy_remains(self) -> None:
        self.assertTrue(make_book(available_copies=1).is_available)

    def test_book_is_not_available_when_every_copy_is_lent(self) -> None:
        self.assertFalse(make_book(available_copies=0).is_available)

    def test_required_text_fields_must_not_be_blank(self) -> None:
        for field_name in ("id", "title", "author", "isbn", "category"):
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    make_book(**{field_name: "   "})

    def test_copy_counts_must_be_non_negative_integers(self) -> None:
        for field_name in ("total_copies", "available_copies"):
            for invalid_value in (-1, 1.5, "2", True):
                with self.subTest(field=field_name, value=invalid_value):
                    with self.assertRaises(ValueError):
                        make_book(**{field_name: invalid_value})

    def test_available_copies_cannot_exceed_total_copies(self) -> None:
        with self.assertRaises(ValueError):
            make_book(available_copies=4, total_copies=3)


if __name__ == "__main__":
    unittest.main()
