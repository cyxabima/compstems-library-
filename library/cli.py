"""Command-line interface for the library management system."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .models import Book
from .repository import DEFAULT_DATA_PATH, BookRepository
from .service import BookService

HEADERS = ("ID", "Title", "Author", "ISBN", "Category", "Available/Total")
EMPTY_CATALOGUE_MESSAGE = "No books in the catalogue."
NO_BOOKS_FOUND_MESSAGE = "No books found"


def format_books(books: Sequence[Book]) -> str:
    """Render the catalogue as an aligned table, one row per book."""
    if not books:
        return EMPTY_CATALOGUE_MESSAGE

    rows: list[tuple[str, ...]] = [HEADERS]
    rows.extend(
        (
            book.id,
            book.title,
            book.author,
            book.isbn,
            book.category,
            f"{book.available_copies}/{book.total_copies}",
        )
        for book in books
    )
    widths = [
        max(len(row[column]) for row in rows) for column in range(len(HEADERS))
    ]

    lines = [
        "  ".join(value.ljust(widths[column]) for column, value in enumerate(row)).rstrip()
        for row in rows
    ]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Library Management System",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_PATH,
        metavar="PATH",
        help="book catalogue JSON file (default: data/books.json)",
    )
    parser.add_argument(
        "--search",
        metavar="QUERY",
        help="search books by title, author, ISBN or category",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the command-line application and return its exit status."""
    args = build_parser().parse_args(argv)
    service = BookService(BookRepository(args.data))

    try:
        if args.search is None:
            books = service.list_books()
        else:
            books = service.search_books(args.search)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.search is not None and not books:
        print(NO_BOOKS_FOUND_MESSAGE)
    else:
        print(format_books(books))
    return 0


def main() -> int:
    return run()
