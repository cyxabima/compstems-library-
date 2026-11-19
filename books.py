"""Validate new books, add them to the catalogue and render the add screen."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from library.models import Book
from library.repository import BookRepository


class BookValidationError(ValueError):
    """Raised when details for a new book are missing or invalid."""


class DuplicateISBNError(BookValidationError):
    """Raised when a book with the same ISBN is already in the catalogue."""


def clean_isbn(isbn: str) -> str:
    """Return an ISBN with surrounding whitespace, spaces and hyphens removed."""
    if not isinstance(isbn, str):
        raise BookValidationError("ISBN must be text")
    return "".join(isbn.split()).replace("-", "")


def validate_book(
    title: str,
    author: str,
    isbn: str,
    category: str,
    copies: int | str,
    *,
    existing_books: Sequence[Book] = (),
) -> tuple[str, str, str, str, int]:
    """Validate a new book and return its normalized details.

    Title, author and ISBN are required. The ISBN must contain exactly 10 or
    13 digits and must not already be in the catalogue. Copies must be at
    least one; a blank category falls back to ``General``.
    """
    clean_title = _required_text(title, "Title")
    clean_author = _required_text(author, "Author")

    if not isinstance(category, str):
        raise BookValidationError("Category must be text")
    clean_category = category.strip() or "General"

    clean_isbn_value = clean_isbn(isbn)
    if len(clean_isbn_value) not in (10, 13) or not clean_isbn_value.isdigit():
        raise BookValidationError("ISBN must be 10 or 13 digits")

    if any(book.isbn == clean_isbn_value for book in existing_books):
        raise DuplicateISBNError(
            f"A book with ISBN {clean_isbn_value} is already in the catalogue"
        )

    return (
        clean_title,
        clean_author,
        clean_isbn_value,
        clean_category,
        _parse_copies(copies),
    )


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BookValidationError(f"{label} is required")
    return value.strip()


def _parse_copies(copies: int | str) -> int:
    if isinstance(copies, bool):
        raise BookValidationError("Copies must be a whole number")

    if isinstance(copies, int):
        value = copies
    elif isinstance(copies, str) and copies.strip().isdigit():
        value = int(copies.strip())
    else:
        raise BookValidationError("Copies must be a whole number")

    if value < 1:
        raise BookValidationError("Copies must be at least 1")
    return value


def _next_book_id(books: Sequence[Book]) -> str:
    numbers = [
        int(book.id[1:])
        for book in books
        if book.id.upper().startswith("B") and book.id[1:].isdigit()
    ]
    return f"B{max(numbers, default=0) + 1:03d}"


def add_book(
    title: str,
    author: str,
    isbn: str,
    category: str,
    copies: int | str,
    *,
    books: BookRepository,
) -> Book:
    """Validate and append a new book, returning the stored record."""
    existing = books.load()
    clean_title, clean_author, clean_isbn_value, clean_category, count = (
        validate_book(
            title,
            author,
            isbn,
            category,
            copies,
            existing_books=existing,
        )
    )

    book = Book(
        id=_next_book_id(existing),
        title=clean_title,
        author=clean_author,
        isbn=clean_isbn_value,
        category=clean_category,
        total_copies=count,
        available_copies=count,
    )
    books.save([*existing, book])
    return book


def ui_add_book(
    books: BookRepository,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> Book | None:
    """Prompt for a new book, returning it or None when validation fails."""
    title = input_fn("Title: ")
    author = input_fn("Author: ")
    isbn = input_fn("ISBN: ")
    category = input_fn("Category [General]: ")
    copies = input_fn("Copies: ")

    try:
        book = add_book(
            title,
            author,
            isbn,
            category,
            copies,
            books=books,
        )
    except ValueError as exc:
        print_fn(f"Error: {exc}")
        return None

    print_fn(
        f"Added '{book.title}' ({book.id}) with {book.total_copies} copies."
    )
    return book
