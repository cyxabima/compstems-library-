"""Show library counts and reset the library data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from library.repository import BookRepository
from loans import LoanRepository, LoanService, ui_list_overdue
from members import MemberRepository


@dataclass(frozen=True, slots=True)
class DashboardStats:
    """Key library counts shown on the dashboard."""

    book_titles: int
    members: int
    active_loans: int
    overdue_loans: int


def stats(
    service: LoanService,
    *,
    as_of: date | None = None,
) -> DashboardStats:
    """Return the library counts for ``as_of`` (today by default)."""
    return DashboardStats(
        book_titles=len(service.list_books()),
        members=len(service.list_members()),
        active_loans=len(service.list_loans()),
        overdue_loans=len(service.list_overdue(as_of=as_of)),
    )


def ui_dashboard(
    service: LoanService,
    *,
    as_of: date | None = None,
    print_fn: Callable[[str], None] = print,
) -> DashboardStats:
    """Print the library counts followed by the list of overdue loans."""
    counts = stats(service, as_of=as_of)

    print_fn("Library dashboard")
    print_fn(f"  Book titles:   {counts.book_titles}")
    print_fn(f"  Members:       {counts.members}")
    print_fn(f"  Books on loan: {counts.active_loans}")
    print_fn(f"  Overdue loans: {counts.overdue_loans}")
    print_fn("")
    print_fn("Overdue loans:")
    ui_list_overdue(service, as_of=as_of, print_fn=print_fn)
    return counts


def ui_reset(
    books: BookRepository,
    loans: LoanRepository,
    members: MemberRepository,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> bool:
    """Clear all library data, but only after the user confirms.

    Returns True when the data was cleared and False when the user cancelled.
    """
    answer = input_fn("Reset all library data? [y/N]: ").strip().casefold()
    if answer not in {"y", "yes"}:
        print_fn("Reset cancelled.")
        return False

    loans.save([])
    members.save([])
    books.save([])
    print_fn("Library data cleared.")
    return True
