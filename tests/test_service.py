"""Tests for catalogue services."""

import unittest

from library.models import Book
from library.service import BookService


class StubRepository:
    """In-memory stand-in for BookRepository."""

    def __init__(self, books: list[Book]) -> None:
        self._books = books

    def load(self) -> list[Book]:
        return list(self._books)


def make_book(book_id: str, title: str) -> Book:
    return Book(
        id=book_id,
        title=title,
        author="An Author",
        isbn="9780000000000",
        category="General",
        total_copies=1,
        available_copies=1,
    )


class BookServiceTests(unittest.TestCase):
    def test_lists_all_books_sorted_by_title(self) -> None:
        service = BookService(
            StubRepository(
                [
                    make_book("B003", "zebra"),
                    make_book("B001", "Apple"),
                    make_book("B002", "banana"),
                ]
            )
        )

        titles = [book.title for book in service.list_books()]

        self.assertEqual(titles, ["Apple", "banana", "zebra"])

    def test_sorting_by_title_ignores_letter_case(self) -> None:
        service = BookService(
            StubRepository(
                [
                    make_book("B001", "beta"),
                    make_book("B002", "Alpha"),
                    make_book("B003", "gamma"),
                ]
            )
        )

        titles = [book.title for book in service.list_books()]

        self.assertEqual(titles, ["Alpha", "beta", "gamma"])

    def test_books_with_the_same_title_are_ordered_by_id(self) -> None:
        service = BookService(
            StubRepository(
                [
                    make_book("B002", "Same Title"),
                    make_book("B001", "Same Title"),
                ]
            )
        )

        ids = [book.id for book in service.list_books()]

        self.assertEqual(ids, ["B001", "B002"])

    def test_empty_catalogue_is_returned_as_an_empty_list(self) -> None:
        self.assertEqual(BookService(StubRepository([])).list_books(), [])


if __name__ == "__main__":
    unittest.main()
