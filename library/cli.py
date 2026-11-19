"""Command-line interface for the library management system."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from books import ui_add_book
from dashboard import ui_dashboard, ui_reset
from loans import (
    DEFAULT_LOANS_PATH,
    LoanRepository,
    LoanService,
    ui_issue_book,
    ui_list_loans,
    ui_list_overdue,
    ui_return_book,
)
from members import DEFAULT_MEMBERS_PATH, MemberRepository

from .models import Book
from .repository import DEFAULT_DATA_PATH, BookRepository
from .service import BookService

HEADERS = ("ID", "Title", "Author", "ISBN", "Category", "Available/Total")
EMPTY_CATALOGUE_MESSAGE = "No books in the catalogue."


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
        "--add-book",
        action="store_true",
        help="open the add-book screen",
    )
    parser.add_argument(
        "--issue",
        action="store_true",
        help="open the issue-book screen",
    )
    parser.add_argument(
        "--return",
        dest="return_book",
        action="store_true",
        help="open the return-book screen",
    )
    parser.add_argument(
        "--list-loans",
        action="store_true",
        help="list active loans",
    )
    parser.add_argument(
        "--show-returned",
        action="store_true",
        help="include returned loans when listing loans",
    )
    parser.add_argument(
        "--overdue",
        action="store_true",
        help="list overdue loans with days late and fines",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="show library counts and overdue loans",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="clear all library data after confirmation",
    )
    parser.add_argument(
        "--members",
        type=Path,
        default=DEFAULT_MEMBERS_PATH,
        metavar="PATH",
        help="member JSON file (default: data/members.json)",
    )
    parser.add_argument(
        "--loans",
        type=Path,
        default=DEFAULT_LOANS_PATH,
        metavar="PATH",
        help="loan JSON file (default: data/loans.json)",
    )
    return parser


def _loan_service(args: argparse.Namespace) -> LoanService:
    return LoanService(
        BookRepository(args.data),
        LoanRepository(args.loans),
        MemberRepository(args.members),
    )


def _run_add_book(args: argparse.Namespace) -> int:
    try:
        book = ui_add_book(BookRepository(args.data))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0 if book is not None else 1


def _run_issue_screen(args: argparse.Namespace) -> int:
    try:
        loan = ui_issue_book(_loan_service(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0 if loan is not None else 1


def _run_return_screen(args: argparse.Namespace) -> int:
    try:
        loan = ui_return_book(_loan_service(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0 if loan is not None else 1


def _run_list_loans(args: argparse.Namespace) -> int:
    try:
        ui_list_loans(
            _loan_service(args),
            include_returned=args.show_returned,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def _run_list_overdue(args: argparse.Namespace) -> int:
    try:
        ui_list_overdue(_loan_service(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def _run_dashboard(args: argparse.Namespace) -> int:
    try:
        ui_dashboard(_loan_service(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def _run_reset(args: argparse.Namespace) -> int:
    try:
        cleared = ui_reset(
            BookRepository(args.data),
            LoanRepository(args.loans),
            MemberRepository(args.members),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0 if cleared else 1


def run(argv: Sequence[str] | None = None) -> int:
    """Run the command-line application and return its exit status."""
    args = build_parser().parse_args(argv)
    if args.add_book:
        return _run_add_book(args)
    if args.issue:
        return _run_issue_screen(args)
    if args.return_book:
        return _run_return_screen(args)
    if args.list_loans:
        return _run_list_loans(args)
    if args.overdue:
        return _run_list_overdue(args)
    if args.dashboard:
        return _run_dashboard(args)
    if args.reset:
        return _run_reset(args)

    service = BookService(BookRepository(args.data))

    try:
        books = service.list_books()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(format_books(books))
    return 0


def main() -> int:
    return run()
