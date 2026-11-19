"""Issue books, record loans and render the issue-book screen."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from library.models import Book
from library.repository import BookRepository
from members import Member, MemberRepository, normalize_email

LOAN_PERIOD_DAYS = 14
MAX_ACTIVE_LOANS = 3
DEFAULT_LOANS_PATH = Path(__file__).resolve().parent / "data" / "loans.json"


class LoanError(ValueError):
    """Base class for loan validation errors."""


class BookNotFoundError(LoanError):
    """Raised when the requested book is not in the catalogue."""


class BookUnavailableError(LoanError):
    """Raised when a book has no copies available to lend."""


class MemberNotFoundError(LoanError):
    """Raised when the requested member is not registered."""


class LoanLimitError(LoanError):
    """Raised when a member already has the maximum active loans."""


@dataclass(frozen=True, slots=True)
class Loan:
    """A recorded loan of one book to one member."""

    id: str
    book_id: str
    member_email: str
    issued_on: date
    due_on: date
    returned_on: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("id must be a non-empty string")
        if not isinstance(self.book_id, str) or not self.book_id.strip():
            raise ValueError("book_id must be a non-empty string")

        object.__setattr__(self, "member_email", normalize_email(self.member_email))

        if not isinstance(self.issued_on, date):
            raise ValueError("issued_on must be a date")
        if not isinstance(self.due_on, date):
            raise ValueError("due_on must be a date")
        expected_due = self.issued_on + timedelta(days=LOAN_PERIOD_DAYS)
        if self.due_on != expected_due:
            raise ValueError(
                f"due_on must be exactly {LOAN_PERIOD_DAYS} days after issued_on"
            )

        if self.returned_on is not None:
            if not isinstance(self.returned_on, date):
                raise ValueError("returned_on must be a date or None")
            if self.returned_on < self.issued_on:
                raise ValueError("returned_on cannot be before issued_on")

    @property
    def is_active(self) -> bool:
        """Return True while the loan has not been returned."""
        return self.returned_on is None


class LoanRepository:
    """Read and write loan records as JSON."""

    def __init__(self, path: str | Path = DEFAULT_LOANS_PATH) -> None:
        self.path = Path(path)

    def load(self) -> list[Loan]:
        """Return recorded loans, or an empty list if the file is missing."""
        if not self.path.exists():
            return []

        try:
            raw = self.path.read_text(encoding="utf-8")
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Loan file {self.path} is not valid JSON: {exc.msg}"
            ) from exc
        except OSError as exc:
            raise ValueError(f"Could not read loan file {self.path}: {exc}") from exc

        if not isinstance(payload, list):
            raise ValueError(f"Loan file {self.path} must contain a JSON list")

        loans: list[Loan] = []
        seen_ids: set[str] = set()
        for position, entry in enumerate(payload, start=1):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Loan entry {position} in {self.path} must be a JSON object"
                )
            try:
                loan = Loan(
                    id=entry["id"],
                    book_id=entry["book_id"],
                    member_email=entry["member_email"],
                    issued_on=self._read_date(entry, "issued_on", position),
                    due_on=self._read_date(entry, "due_on", position),
                    returned_on=self._read_optional_date(
                        entry, "returned_on", position
                    ),
                )
            except KeyError as exc:
                raise ValueError(
                    f"Loan entry {position} in {self.path} is missing {exc.args[0]}"
                ) from exc
            except TypeError as exc:
                raise ValueError(
                    f"Loan entry {position} in {self.path} does not match "
                    f"the loan schema: {exc}"
                ) from exc
            except ValueError as exc:
                raise ValueError(
                    f"Loan entry {position} in {self.path} is invalid: {exc}"
                ) from exc

            if loan.id in seen_ids:
                raise ValueError(
                    f"Loan entry {position} in {self.path} duplicates id {loan.id}"
                )
            seen_ids.add(loan.id)
            loans.append(loan)

        return loans

    def save(self, loans: Iterable[Loan]) -> None:
        """Write loan records to disk, creating the directory if needed."""
        payload = [
            {
                "id": loan.id,
                "book_id": loan.book_id,
                "member_email": loan.member_email,
                "issued_on": loan.issued_on.isoformat(),
                "due_on": loan.due_on.isoformat(),
                "returned_on": (
                    loan.returned_on.isoformat() if loan.returned_on else None
                ),
            }
            for loan in loans
        ]
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"Could not save loan file {self.path}: {exc}") from exc

    def _read_date(self, entry: dict[str, Any], field: str, position: int) -> date:
        value = entry[field]
        if not isinstance(value, str):
            raise ValueError(
                f"loan entry {position} in {self.path} has a non-text {field}"
            )
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"loan entry {position} in {self.path} has an invalid {field}"
            ) from exc

    def _read_optional_date(
        self, entry: dict[str, Any], field: str, position: int
    ) -> date | None:
        value = entry.get(field)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(
                f"loan entry {position} in {self.path} has a non-text {field}"
            )
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"loan entry {position} in {self.path} has an invalid {field}"
            ) from exc


def _next_loan_id(loans: Sequence[Loan]) -> str:
    numbers = [
        int(loan.id[1:])
        for loan in loans
        if loan.id.startswith("L") and loan.id[1:].isdigit()
    ]
    return f"L{max(numbers, default=0) + 1:03d}"


class LoanService:
    """Apply loan rules and keep books and loans in sync."""

    def __init__(
        self,
        books: BookRepository,
        loans: LoanRepository,
        members: MemberRepository,
    ) -> None:
        self._books = books
        self._loans = loans
        self._members = members

    def list_available_books(self) -> list[Book]:
        """Return lendable books sorted by title."""
        return sorted(
            (book for book in self._books.load() if book.is_available),
            key=lambda book: (book.title.casefold(), book.id),
        )

    def list_members(self) -> list[Member]:
        """Return registered members sorted by name."""
        return sorted(
            self._members.load(),
            key=lambda member: (member.name.casefold(), member.email),
        )

    def active_loans_for(self, member_email: str) -> list[Loan]:
        """Return the member's loans that have not been returned."""
        email = normalize_email(member_email)
        return [
            loan
            for loan in self._loans.load()
            if loan.is_active and loan.member_email == email
        ]

    def issue_book(
        self,
        book_id: str,
        member_email: str,
        *,
        issued_on: date | None = None,
    ) -> Loan:
        """Issue one available copy and record a 14-day loan."""
        email = normalize_email(member_email)
        member = next(
            (member for member in self._members.load() if member.email == email),
            None,
        )
        if member is None:
            raise MemberNotFoundError(f"No member is registered with email {email}")

        books = self._books.load()
        book_index = next(
            (
                index
                for index, book in enumerate(books)
                if book.id.casefold() == book_id.strip().casefold()
            ),
            None,
        )
        if book_index is None:
            raise BookNotFoundError(f"Book {book_id!r} was not found")

        book = books[book_index]
        if not book.is_available:
            raise BookUnavailableError(
                f"'{book.title}' has no available copies"
            )

        loans = self._loans.load()
        active_loans = [
            loan
            for loan in loans
            if loan.is_active and loan.member_email == email
        ]
        if len(active_loans) >= MAX_ACTIVE_LOANS:
            raise LoanLimitError(
                f"{member.name} already has {MAX_ACTIVE_LOANS} active loans"
            )

        issue_date = issued_on or date.today()
        loan = Loan(
            id=_next_loan_id(loans),
            book_id=book.id,
            member_email=email,
            issued_on=issue_date,
            due_on=issue_date + timedelta(days=LOAN_PERIOD_DAYS),
        )

        updated_books = list(books)
        updated_books[book_index] = replace(
            book,
            available_copies=book.available_copies - 1,
        )

        self._books.save(updated_books)
        try:
            self._loans.save([*loans, loan])
        except Exception:
            self._books.save(books)
            raise

        return loan


def issue_book(
    book_id: str,
    member_email: str,
    *,
    books: BookRepository,
    loans: LoanRepository,
    members: MemberRepository,
    issued_on: date | None = None,
) -> Loan:
    """Convenience wrapper around :meth:`LoanService.issue_book`."""
    return LoanService(books, loans, members).issue_book(
        book_id,
        member_email,
        issued_on=issued_on,
    )


def _select_member(choice: str, members: Sequence[Member]) -> Member | None:
    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(members):
            return members[index - 1]
        return None

    email = choice.strip().casefold()
    return next((member for member in members if member.email == email), None)


def ui_issue_book(
    service: LoanService,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
    issued_on: date | None = None,
) -> Loan | None:
    """Run the interactive issue-book screen, returning the created loan."""
    available_books = service.list_available_books()
    if not available_books:
        print_fn("No books with available copies.")
        return None

    print_fn("Available books:")
    for book in available_books:
        print_fn(
            f"  {book.id}  {book.title}  "
            f"({book.available_copies}/{book.total_copies})"
        )

    members = service.list_members()
    if not members:
        print_fn("No members registered.")
        return None

    print_fn("Members:")
    for index, member in enumerate(members, start=1):
        print_fn(f"  {index}. {member.name} <{member.email}>")

    book_id = input_fn("Book ID: ").strip()
    member_choice = input_fn("Member number or email: ").strip()
    member = _select_member(member_choice, members)
    if member is None:
        print_fn("Error: Member not found.")
        return None

    try:
        loan = service.issue_book(book_id, member.email, issued_on=issued_on)
    except ValueError as exc:
        print_fn(f"Error: {exc}")
        return None

    title_by_id = {book.id.casefold(): book.title for book in available_books}
    title = title_by_id.get(loan.book_id.casefold(), loan.book_id)
    print_fn(
        f"Issued '{title}' to {member.name}. Due {loan.due_on.isoformat()}."
    )
    return loan
