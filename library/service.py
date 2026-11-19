"""Catalogue operations used by the user interface."""

from .models import Book
from .repository import BookRepository


class BookService:
    """Provide read operations over the book catalogue."""

    def __init__(self, repository: BookRepository) -> None:
        self._repository = repository

    def list_books(self) -> list[Book]:
        """Return every book sorted by title, ignoring letter case."""
        return sorted(
            self._repository.load(),
            key=lambda book: (book.title.casefold(), book.id),
        )
