"""Tests for issuing books and the issue-book screen."""

import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from library.models import Book
from library.repository import BookRepository
from loans import (
    LOAN_PERIOD_DAYS,
    MAX_ACTIVE_LOANS,
    BookNotFoundError,
    BookUnavailableError,
    Loan,
    LoanLimitError,
    LoanRepository,
    LoanService,
    MemberNotFoundError,
    issue_book,
    ui_issue_book,
)
from members import Member, MemberRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_book(
    book_id: str = "B001",
    title: str = "Alpha",
    *,
    available_copies: int = 1,
    total_copies: int = 2,
) -> Book:
    return Book(
        id=book_id,
        title=title,
        author="An Author",
        isbn="9780000000000",
        category="General",
        total_copies=total_copies,
        available_copies=available_copies,
    )


class LibraryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        self.books = BookRepository(root / "books.json")
        self.loans = LoanRepository(root / "loans.json")
        self.member_store = MemberRepository(root / "members.json")
        self.member_store.save(
            [
                Member("Ada Lovelace", "ada@example.com"),
                Member("Grace Hopper", "grace@example.com"),
            ]
        )
        self.service = LoanService(self.books, self.loans, self.member_store)

    def add_books(self, *books: Book) -> None:
        self.books.save(books)

    def run_ui(
        self, answers: list[str], issued_on: date | None = None
    ) -> tuple[Loan | None, list[str]]:
        answer_iter = iter(answers)
        output: list[str] = []
        loan = ui_issue_book(
            self.service,
            input_fn=lambda _prompt: next(answer_iter),
            print_fn=output.append,
            issued_on=issued_on,
        )
        return loan, output


class IssueBookTests(LibraryTestCase):
    def test_issues_available_book_and_records_loan(self) -> None:
        self.add_books(make_book())
        issued_on = date(2026, 11, 19)

        loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=issued_on
        )

        self.assertEqual(loan.id, "L001")
        self.assertEqual(loan.book_id, "B001")
        self.assertEqual(loan.member_email, "ada@example.com")
        self.assertEqual(loan.issued_on, issued_on)
        self.assertTrue(loan.is_active)
        self.assertEqual(self.loans.load(), [loan])

    def test_due_date_is_exactly_fourteen_days_after_issue(self) -> None:
        self.add_books(make_book())
        issued_on = date(2026, 11, 19)

        loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=issued_on
        )

        self.assertEqual(LOAN_PERIOD_DAYS, 14)
        self.assertEqual(loan.due_on, issued_on + timedelta(days=14))
        self.assertEqual(loan.due_on, date(2026, 12, 3))

    def test_available_count_drops_by_one_and_is_persisted(self) -> None:
        self.add_books(make_book(available_copies=3, total_copies=4))

        self.service.issue_book("B001", "ada@example.com")

        stored_book = self.books.load()[0]
        self.assertEqual(stored_book.available_copies, 2)
        self.assertEqual(stored_book.total_copies, 4)

    def test_only_available_books_are_listed(self) -> None:
        self.add_books(
            make_book("B001", "Zebra", available_copies=1),
            make_book("B002", "Alpha", available_copies=2),
            make_book("B003", "Unavailable", available_copies=0),
        )

        available = self.service.list_available_books()

        self.assertEqual([book.id for book in available], ["B002", "B001"])

    def test_rejects_a_book_without_available_copies(self) -> None:
        self.add_books(make_book(available_copies=0, total_copies=2))

        with self.assertRaisesRegex(BookUnavailableError, "no available copies"):
            self.service.issue_book("B001", "ada@example.com")

        self.assertEqual(self.loans.load(), [])
        self.assertEqual(self.books.load()[0].available_copies, 0)

    def test_rejects_an_unknown_book(self) -> None:
        self.add_books(make_book())

        with self.assertRaisesRegex(BookNotFoundError, "was not found"):
            self.service.issue_book("B999", "ada@example.com")

        self.assertEqual(self.loans.load(), [])

    def test_rejects_an_unknown_member(self) -> None:
        self.add_books(make_book())

        with self.assertRaisesRegex(MemberNotFoundError, "No member"):
            self.service.issue_book("B001", "nobody@example.com")

        self.assertEqual(self.loans.load(), [])

    def test_member_may_have_at_most_three_active_loans(self) -> None:
        self.add_books(
            make_book("B001", "Book 1"),
            make_book("B002", "Book 2"),
            make_book("B003", "Book 3"),
            make_book("B004", "Book 4"),
        )
        issued_on = date(2026, 11, 19)

        for book_id in ("B001", "B002", "B003"):
            self.service.issue_book(
                book_id, "ada@example.com", issued_on=issued_on
            )

        with self.assertRaisesRegex(LoanLimitError, "3 active loans"):
            self.service.issue_book("B004", "ada@example.com", issued_on=issued_on)

        self.assertEqual(len(self.loans.load()), MAX_ACTIVE_LOANS)
        self.assertEqual(self.books.load()[3].available_copies, 1)
        self.assertEqual(
            len(self.service.active_loans_for("ada@example.com")),
            MAX_ACTIVE_LOANS,
        )

    def test_returned_loans_do_not_count_towards_the_limit(self) -> None:
        self.add_books(
            make_book("B001", "Book 1"),
            make_book("B002", "Book 2"),
            make_book("B003", "Book 3"),
            make_book("B004", "Book 4"),
        )
        issued_on = date(2026, 11, 19)
        for book_id in ("B001", "B002", "B003"):
            self.service.issue_book(
                book_id, "ada@example.com", issued_on=issued_on
            )

        loans = self.loans.load()
        loans[0] = replace(
            loans[0],
            returned_on=loans[0].issued_on + timedelta(days=2),
        )
        self.loans.save(loans)

        loan = self.service.issue_book(
            "B004", "ada@example.com", issued_on=issued_on
        )

        self.assertEqual(loan.book_id, "B004")
        self.assertEqual(len(self.service.active_loans_for("ada@example.com")), 3)

    def test_module_level_issue_book_uses_the_same_rules(self) -> None:
        self.add_books(make_book())

        loan = issue_book(
            "B001",
            "ada@example.com",
            books=self.books,
            loans=self.loans,
            members=self.member_store,
            issued_on=date(2026, 11, 19),
        )

        self.assertEqual(loan.due_on, date(2026, 12, 3))
        self.assertEqual(len(self.loans.load()), 1)


class LoanRepositoryTests(LibraryTestCase):
    def test_missing_loan_file_is_empty(self) -> None:
        self.assertEqual(self.loans.load(), [])

    def test_saved_loans_can_be_loaded_again(self) -> None:
        loan = Loan(
            id="L001",
            book_id="B001",
            member_email="ada@example.com",
            issued_on=date(2026, 11, 19),
            due_on=date(2026, 12, 3),
        )

        self.loans.save([loan])

        self.assertEqual(self.loans.load(), [loan])

    def test_loan_rejects_a_due_date_other_than_fourteen_days(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 14 days"):
            Loan(
                id="L001",
                book_id="B001",
                member_email="ada@example.com",
                issued_on=date(2026, 11, 19),
                due_on=date(2026, 12, 2),
            )


class IssueBookScreenTests(LibraryTestCase):
    def test_lists_only_available_books_and_issues_to_selected_member(self) -> None:
        self.add_books(
            make_book("B001", "Alpha", available_copies=1),
            make_book("B002", "Unavailable", available_copies=0),
        )

        loan, output = self.run_ui(["B001", "1"], issued_on=date(2026, 11, 19))

        self.assertIsNotNone(loan)
        self.assertTrue(any("B001" in line for line in output))
        self.assertFalse(any("B002" in line for line in output))
        self.assertIn("  1. Ada Lovelace <ada@example.com>", output)
        self.assertEqual(
            output[-1],
            "Issued 'Alpha' to Ada Lovelace. Due 2026-12-03.",
        )
        self.assertEqual(self.books.load()[0].available_copies, 0)

    def test_can_select_a_member_by_email(self) -> None:
        self.add_books(make_book())

        loan, _output = self.run_ui(["B001", "GRACE@example.com"])

        self.assertIsNotNone(loan)
        self.assertEqual(loan.member_email, "grace@example.com")

    def test_reports_validation_failures_clearly(self) -> None:
        self.add_books(
            make_book("B001", "Alpha", available_copies=1),
            make_book("B002", "Unavailable", available_copies=0),
        )

        loan, output = self.run_ui(["B002", "1"])

        self.assertIsNone(loan)
        self.assertTrue(output[-1].startswith("Error:"))
        self.assertIn("no available copies", output[-1])
        self.assertEqual(self.loans.load(), [])

    def test_reports_an_unknown_member_selection(self) -> None:
        self.add_books(make_book())

        loan, output = self.run_ui(["B001", "99"])

        self.assertIsNone(loan)
        self.assertEqual(output[-1], "Error: Member not found.")

    def test_reports_when_no_books_are_available(self) -> None:
        self.add_books(make_book(available_copies=0))

        loan, output = self.run_ui([])

        self.assertIsNone(loan)
        self.assertEqual(output, ["No books with available copies."])

    def test_reports_when_no_members_are_registered(self) -> None:
        self.add_books(make_book())
        self.member_store.save([])

        loan, output = self.run_ui([])

        self.assertIsNone(loan)
        self.assertEqual(output[-1], "No members registered.")


class IssueBookCommandTests(LibraryTestCase):
    def run_command(self, *arguments: str, stdin: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "main.py",
                "--issue",
                "--data",
                str(self.books.path),
                "--members",
                str(self.member_store.path),
                "--loans",
                str(self.loans.path),
                *arguments,
            ],
            cwd=PROJECT_ROOT,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_issue_command_records_the_loan(self) -> None:
        self.add_books(make_book())

        result = self.run_command(stdin="B001\n1\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Issued 'Alpha' to Ada Lovelace. Due ", result.stdout)
        self.assertEqual(self.books.load()[0].available_copies, 0)
        self.assertEqual(len(self.loans.load()), 1)

    def test_issue_command_returns_an_error_for_invalid_choices(self) -> None:
        self.add_books(make_book())

        result = self.run_command(stdin="B999\n1\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Error:", result.stdout)
        self.assertIn("was not found", result.stdout)
        self.assertEqual(self.loans.load(), [])


if __name__ == "__main__":
    unittest.main()
