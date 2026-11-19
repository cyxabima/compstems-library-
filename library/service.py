"""Catalogue operations used by the user interface."""

from .models import Book
from .repository import BookRepository


def _title_sort_key(book: Book) -> tuple[str, str]:
    return (book.title.casefold(), book.id)


class BookService:
    """Provide read operations over the book catalogue."""

    def __init__(self, repository: BookRepository) -> None:
        self._repository = repository

    def list_books(self) -> list[Book]:
        """Return every book sorted by title, ignoring letter case."""
        return sorted(self._repository.load(), key=_title_sort_key)

    def search_books(self, query: str) -> list[Book]:
        """Return books whose title, author, ISBN or category contains the query.

        Matching is case-insensitive and the results keep title order. A blank
        query returns no books so the interface can show its empty state.
        """
        term = query.strip().casefold()
        if not term:
            return []

        return [
            book
            for book in self.list_books()
            if any(
                term in value.casefold()
                for value in (
                    book.title,
                    book.author,
                    book.isbn,
                    book.category,
                )
            )
        ]
