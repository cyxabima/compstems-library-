"""Tests for issuing books and the issue-book screen."""

import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from books import (
    BookValidationError,
    DuplicateISBNError,
    add_book,
    clean_isbn,
    ui_add_book,
    validate_book,
)
from dashboard import DashboardStats, stats, ui_dashboard, ui_reset
from library.models import Book
from library.repository import BookRepository
from loans import (
    FINE_PER_DAY,
    LOAN_HEADERS,
    LOAN_PERIOD_DAYS,
    MAX_ACTIVE_LOANS,
    OVERDUE_HEADERS,
    BookNotFoundError,
    BookUnavailableError,
    Loan,
    LoanAlreadyReturnedError,
    LoanError,
    LoanLimitError,
    LoanNotFoundError,
    LoanRepository,
    LoanService,
    MemberNotFoundError,
    issue_book,
    loan_rows,
    overdue_rows,
    return_book,
    ui_issue_book,
    ui_list_loans,
    ui_list_overdue,
    ui_return_book,
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


class ReturnBookTests(LibraryTestCase):
    def issue_one(self) -> Loan:
        self.add_books(make_book(available_copies=1, total_copies=2))
        return self.service.issue_book(
            "B001",
            "ada@example.com",
            issued_on=date(2026, 11, 19),
        )

    def test_returns_loan_by_id_and_raises_available_count(self) -> None:
        loan = self.issue_one()
        self.assertEqual(self.books.load()[0].available_copies, 0)

        returned = self.service.return_book(
            loan.id,
            returned_on=date(2026, 11, 20),
        )

        self.assertEqual(returned.id, loan.id)
        self.assertFalse(returned.is_active)
        self.assertEqual(returned.returned_on, date(2026, 11, 20))
        self.assertEqual(self.books.load()[0].available_copies, 1)
        self.assertEqual(self.loans.load(), [returned])

    def test_loan_id_lookup_ignores_letter_case(self) -> None:
        loan = self.issue_one()

        returned = self.service.return_book(
            loan.id.lower(),
            returned_on=date(2026, 11, 20),
        )

        self.assertEqual(returned.id, loan.id)

    def test_rejects_an_unknown_loan_id(self) -> None:
        self.issue_one()

        with self.assertRaisesRegex(LoanNotFoundError, "was not found"):
            self.service.return_book("L999")

        self.assertEqual(self.books.load()[0].available_copies, 0)

    def test_rejects_a_loan_that_was_already_returned(self) -> None:
        loan = self.issue_one()
        self.service.return_book(loan.id, returned_on=date(2026, 11, 20))

        with self.assertRaisesRegex(LoanAlreadyReturnedError, "already returned"):
            self.service.return_book(loan.id, returned_on=date(2026, 11, 21))

        self.assertEqual(self.books.load()[0].available_copies, 1)
        self.assertEqual(len(self.loans.load()), 1)

    def test_rejects_a_return_date_before_the_issue_date(self) -> None:
        loan = self.issue_one()

        with self.assertRaisesRegex(LoanError, "cannot be before"):
            self.service.return_book(loan.id, returned_on=date(2026, 11, 18))

        self.assertTrue(self.loans.load()[0].is_active)

    def test_module_level_return_book(self) -> None:
        loan = self.issue_one()

        returned = return_book(
            loan.id,
            books=self.books,
            loans=self.loans,
            returned_on=date(2026, 11, 20),
        )

        self.assertFalse(returned.is_active)


class LoanListTests(LibraryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_books(
            make_book("B001", "Alpha", available_copies=1, total_copies=2),
            make_book("B002", "Beta", available_copies=1, total_copies=2),
        )
        self.first_loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 19)
        )
        self.second_loan = self.service.issue_book(
            "B002", "grace@example.com", issued_on=date(2026, 11, 19)
        )
        self.returned_loan = self.service.return_book(
            self.first_loan.id, returned_on=date(2026, 11, 20)
        )

    def test_headers_describe_the_loan_table(self) -> None:
        self.assertEqual(
            LOAN_HEADERS,
            ("Loan ID", "Book", "Member", "Issued", "Due", "Returned"),
        )

    def test_rows_show_active_loans_by_default(self) -> None:
        rows = loan_rows(
            self.loans.load(),
            books=self.books.load(),
            members=self.member_store.load(),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            (
                self.second_loan.id,
                "Beta",
                "Grace Hopper",
                "2026-11-19",
                "2026-12-03",
                "-",
            ),
        )

    def test_rows_include_returned_loans_when_requested(self) -> None:
        rows = loan_rows(
            self.loans.load(),
            books=self.books.load(),
            members=self.member_store.load(),
            include_returned=True,
        )

        self.assertEqual([row[0] for row in rows], ["L001", "L002"])
        returned_row = rows[0]
        self.assertEqual(returned_row[1], "Alpha")
        self.assertEqual(returned_row[2], "Ada Lovelace")
        self.assertEqual(returned_row[5], "2026-11-20")

    def test_service_filters_loans_by_active_state(self) -> None:
        self.assertEqual(
            [loan.id for loan in self.service.list_loans()],
            [self.second_loan.id],
        )
        self.assertEqual(
            [loan.id for loan in self.service.list_loans(include_returned=True)],
            [self.first_loan.id, self.second_loan.id],
        )

    def test_ui_lists_only_active_loans_by_default(self) -> None:
        output: list[str] = []

        displayed = ui_list_loans(self.service, print_fn=output.append)

        text = "\n".join(output)
        self.assertEqual([loan.id for loan in displayed], [self.second_loan.id])
        self.assertIn(self.second_loan.id, text)
        self.assertNotIn(self.first_loan.id, text)

    def test_ui_includes_returned_loans_when_requested(self) -> None:
        output: list[str] = []

        ui_list_loans(
            self.service,
            include_returned=True,
            print_fn=output.append,
        )

        text = "\n".join(output)
        self.assertIn(self.first_loan.id, text)
        self.assertIn(self.second_loan.id, text)
        self.assertIn("2026-11-20", text)


class OverdueLoanTests(LibraryTestCase):
    def make_loan(self, *, returned_on: date | None = None) -> Loan:
        due_on = date(2026, 12, 3)
        return Loan(
            id="L001",
            book_id="B001",
            member_email="ada@example.com",
            issued_on=due_on - timedelta(days=LOAN_PERIOD_DAYS),
            due_on=due_on,
            returned_on=returned_on,
        )

    def test_days_late_is_zero_on_or_before_the_due_date(self) -> None:
        loan = self.make_loan()

        self.assertEqual(loan.days_late(date(2026, 12, 2)), 0)
        self.assertEqual(loan.days_late(date(2026, 12, 3)), 0)
        self.assertFalse(loan.is_overdue(date(2026, 12, 3)))

    def test_days_late_counts_days_after_the_due_date(self) -> None:
        loan = self.make_loan()

        self.assertEqual(loan.days_late(date(2026, 12, 6)), 3)
        self.assertTrue(loan.is_overdue(date(2026, 12, 6)))

    def test_fine_is_ten_rupees_per_day_late(self) -> None:
        loan = self.make_loan()

        self.assertEqual(FINE_PER_DAY, 10)
        self.assertEqual(loan.fine_for(date(2026, 12, 3)), 0)
        self.assertEqual(loan.fine_for(date(2026, 12, 6)), 30)

    def test_returned_loan_is_measured_at_its_return_date(self) -> None:
        loan = self.make_loan(returned_on=date(2026, 12, 8))

        self.assertEqual(loan.days_late(), 5)
        self.assertEqual(loan.fine_for(), 50)
        self.assertFalse(loan.is_overdue())

    def test_service_lists_only_active_overdue_loans(self) -> None:
        self.add_books(
            make_book("B001", "Alpha", available_copies=2, total_copies=3),
            make_book("B002", "Beta", available_copies=1, total_copies=2),
        )
        overdue = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 1)
        )
        self.service.issue_book(
            "B002", "grace@example.com", issued_on=date(2026, 11, 19)
        )

        overdue_loans = self.service.list_overdue(as_of=date(2026, 11, 18))

        self.assertEqual([loan.id for loan in overdue_loans], [overdue.id])
        self.assertEqual(overdue_loans[0].days_late(date(2026, 11, 18)), 3)


class OverdueScreenTests(LibraryTestCase):
    def test_rows_mark_loans_overdue_with_days_late_and_fine(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 1)
        )

        rows = overdue_rows(
            self.loans.load(),
            books=self.books.load(),
            members=self.member_store.load(),
            as_of=date(2026, 11, 18),
        )

        self.assertEqual(
            rows,
            [
                (
                    loan.id,
                    "Alpha",
                    "Ada Lovelace",
                    "2026-11-15",
                    "3",
                    "30",
                    "OVERDUE",
                )
            ],
        )

    def test_overdue_headers_describe_days_late_and_fine(self) -> None:
        self.assertIn("Days Late", OVERDUE_HEADERS)
        self.assertIn("Fine (Rs)", OVERDUE_HEADERS)
        self.assertIn("Status", OVERDUE_HEADERS)

    def test_ui_lists_overdue_loans_marked_overdue(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 1)
        )
        output: list[str] = []

        displayed = ui_list_overdue(
            self.service,
            as_of=date(2026, 11, 18),
            print_fn=output.append,
        )

        text = "\n".join(output)
        self.assertEqual([item.id for item in displayed], [loan.id])
        self.assertIn("OVERDUE", text)
        self.assertIn("Days Late", text)
        self.assertIn("Fine (Rs)", text)
        self.assertIn("30", text)

    def test_ui_reports_when_no_loans_are_overdue(self) -> None:
        output: list[str] = []

        displayed = ui_list_overdue(
            self.service,
            as_of=date(2026, 11, 18),
            print_fn=output.append,
        )

        self.assertEqual(displayed, [])
        self.assertEqual(output, ["No overdue loans."])


class LateReturnFineTests(LibraryTestCase):
    def test_shows_the_fine_when_an_overdue_book_is_returned(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 19)
        )
        output: list[str] = []

        returned = ui_return_book(
            self.service,
            input_fn=lambda _prompt: loan.id,
            print_fn=output.append,
            returned_on=date(2026, 12, 6),
        )

        self.assertIsNotNone(returned)
        self.assertEqual(returned.days_late(), 3)
        self.assertEqual(returned.fine_for(), 30)
        self.assertIn("Overdue by 3 day(s). Fine: Rs 30.", output)

    def test_has_no_fine_when_returned_by_the_due_date(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 19)
        )
        output: list[str] = []

        returned = ui_return_book(
            self.service,
            input_fn=lambda _prompt: loan.id,
            print_fn=output.append,
            returned_on=date(2026, 11, 30),
        )

        self.assertIsNotNone(returned)
        self.assertEqual(returned.fine_for(), 0)
        self.assertFalse(any("Fine" in line for line in output))


class ReturnBookScreenTests(LibraryTestCase):
    def test_accepts_a_loan_id_and_returns_the_book(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 19)
        )
        output: list[str] = []

        returned = ui_return_book(
            self.service,
            input_fn=lambda _prompt: loan.id,
            print_fn=output.append,
            returned_on=date(2026, 11, 20),
        )

        self.assertIsNotNone(returned)
        self.assertIn("Active loans:", output)
        self.assertEqual(
            output[-1],
            "Returned 'Alpha' (loan L001). Available copies: 1/2.",
        )
        self.assertEqual(self.books.load()[0].available_copies, 1)

    def test_reports_an_unknown_loan_id(self) -> None:
        self.add_books(make_book())
        self.service.issue_book("B001", "ada@example.com")
        output: list[str] = []

        returned = ui_return_book(
            self.service,
            input_fn=lambda _prompt: "L999",
            print_fn=output.append,
        )

        self.assertIsNone(returned)
        self.assertTrue(output[-1].startswith("Error:"))
        self.assertIn("was not found", output[-1])

    def test_reports_when_there_are_no_active_loans(self) -> None:
        output: list[str] = []

        returned = ui_return_book(
            self.service,
            input_fn=lambda _prompt: self.fail("should not prompt"),
            print_fn=output.append,
        )

        self.assertIsNone(returned)
        self.assertEqual(output, ["No active loans."])


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


class DashboardTests(LibraryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_books(
            make_book("B001", "Alpha", available_copies=2, total_copies=3),
            make_book("B002", "Beta", available_copies=1, total_copies=2),
        )
        self.overdue_loan = self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 1)
        )
        self.active_loan = self.service.issue_book(
            "B002", "grace@example.com", issued_on=date(2026, 11, 19)
        )

    def test_stats_count_titles_members_loans_and_overdue(self) -> None:
        counts = stats(self.service, as_of=date(2026, 11, 18))

        self.assertEqual(
            counts,
            DashboardStats(
                book_titles=2,
                members=2,
                active_loans=2,
                overdue_loans=1,
            ),
        )

    def test_ui_shows_counts_and_lists_overdue_loans(self) -> None:
        output: list[str] = []

        counts = ui_dashboard(
            self.service,
            as_of=date(2026, 11, 18),
            print_fn=output.append,
        )

        text = "\n".join(output)
        self.assertEqual(counts.overdue_loans, 1)
        self.assertIn("Library dashboard", text)
        self.assertIn("Book titles:   2", text)
        self.assertIn("Members:       2", text)
        self.assertIn("Books on loan: 2", text)
        self.assertIn("Overdue loans: 1", text)
        self.assertIn(self.overdue_loan.id, text)
        self.assertNotIn(self.active_loan.id, text)
        self.assertIn("OVERDUE", text)


class ResetTests(LibraryTestCase):
    def seed(self) -> None:
        self.add_books(make_book())
        self.service.issue_book(
            "B001", "ada@example.com", issued_on=date(2026, 11, 19)
        )

    def test_declining_confirmation_keeps_all_data(self) -> None:
        self.seed()
        output: list[str] = []

        cleared = ui_reset(
            self.books,
            self.loans,
            self.member_store,
            input_fn=lambda _prompt: "",
            print_fn=output.append,
        )

        self.assertFalse(cleared)
        self.assertEqual(output, ["Reset cancelled."])
        self.assertEqual(len(self.books.load()), 1)
        self.assertEqual(len(self.loans.load()), 1)
        self.assertEqual(len(self.member_store.load()), 2)

    def test_confirming_clears_all_data(self) -> None:
        self.seed()
        output: list[str] = []

        cleared = ui_reset(
            self.books,
            self.loans,
            self.member_store,
            input_fn=lambda _prompt: "yes",
            print_fn=output.append,
        )

        self.assertTrue(cleared)
        self.assertEqual(output, ["Library data cleared."])
        self.assertEqual(self.books.load(), [])
        self.assertEqual(self.loans.load(), [])
        self.assertEqual(self.member_store.load(), [])


class CleanISBNTests(unittest.TestCase):
    def test_removes_spaces_and_hyphens(self) -> None:
        self.assertEqual(clean_isbn(" 978-0-13-235088-4 "), "9780132350884")

    def test_keeps_a_ten_digit_isbn(self) -> None:
        self.assertEqual(clean_isbn("0-306-40615-2"), "0306406152")

    def test_rejects_non_text_input(self) -> None:
        with self.assertRaisesRegex(BookValidationError, "must be text"):
            clean_isbn(9780132350884)  # type: ignore[arg-type]


class ValidateBookTests(unittest.TestCase):
    def test_accepts_a_valid_thirteen_digit_book(self) -> None:
        self.assertEqual(
            validate_book(
                "  Clean Code  ",
                " Robert C. Martin ",
                "978-0-13-235088-4",
                "",
                "3",
            ),
            (
                "Clean Code",
                "Robert C. Martin",
                "9780132350884",
                "General",
                3,
            ),
        )

    def test_accepts_a_ten_digit_isbn(self) -> None:
        _, _, isbn, _, copies = validate_book(
            "Clean Code",
            "Robert C. Martin",
            "0-306-40615-2",
            "Software Engineering",
            1,
        )

        self.assertEqual(isbn, "0306406152")
        self.assertEqual(copies, 1)

    def test_requires_a_title(self) -> None:
        with self.assertRaisesRegex(BookValidationError, "Title is required"):
            validate_book("   ", "An Author", "9780132350884", "General", 1)

    def test_requires_an_author(self) -> None:
        with self.assertRaisesRegex(BookValidationError, "Author is required"):
            validate_book("A Title", "", "9780132350884", "General", 1)

    def test_rejects_isbns_that_are_not_ten_or_thirteen_digits(self) -> None:
        for isbn in (
            "",
            "123456789",
            "123456789012",
            "12345678901a",
            "978-0-13-235088",
        ):
            with self.subTest(isbn=isbn):
                with self.assertRaisesRegex(
                    BookValidationError, "10 or 13 digits"
                ):
                    validate_book("A Title", "An Author", isbn, "General", 1)

    def test_copies_must_be_at_least_one(self) -> None:
        for copies in (0, -1, "0", "many"):
            with self.subTest(copies=copies):
                with self.assertRaisesRegex(
                    BookValidationError, "Copies must be"
                ):
                    validate_book(
                        "A Title", "An Author", "9780132350884", "General", copies
                    )

    def test_rejects_a_duplicate_isbn(self) -> None:
        existing = make_book()
        existing = replace(existing, isbn="9780132350884")

        with self.assertRaisesRegex(DuplicateISBNError, "already in the catalogue"):
            validate_book(
                "Another Book",
                "Another Author",
                "978-0-13-235088-4",
                "General",
                1,
                existing_books=[existing],
            )


class AddBookTests(LibraryTestCase):
    def test_adds_a_valid_book_to_storage(self) -> None:
        book = add_book(
            "Clean Code",
            "Robert C. Martin",
            "978-0-13-235088-4",
            "Software Engineering",
            3,
            books=self.books,
        )

        self.assertEqual(book.id, "B001")
        self.assertEqual(book.isbn, "9780132350884")
        self.assertEqual(book.total_copies, 3)
        self.assertEqual(book.available_copies, 3)
        self.assertEqual(self.books.load(), [book])

    def test_assigns_the_next_book_id(self) -> None:
        self.add_books(
            make_book("B001"),
            make_book("B006", "Beta"),
        )

        book = add_book(
            "Gamma",
            "An Author",
            "9780132350884",
            "General",
            2,
            books=self.books,
        )

        self.assertEqual(book.id, "B007")
        self.assertEqual(len(self.books.load()), 3)

    def test_rejects_an_invalid_book_without_saving(self) -> None:
        with self.assertRaises(BookValidationError):
            add_book(
                "Clean Code",
                "Robert C. Martin",
                "12345",
                "General",
                1,
                books=self.books,
            )

        self.assertEqual(self.books.load(), [])

    def test_rejects_a_duplicate_isbn_without_saving(self) -> None:
        self.add_books(make_book("B001"))

        with self.assertRaises(DuplicateISBNError):
            add_book(
                "Clean Code",
                "Robert C. Martin",
                "9780000000000",
                "General",
                1,
                books=self.books,
            )

        self.assertEqual(len(self.books.load()), 1)


class AddBookScreenTests(LibraryTestCase):
    def test_prompts_for_each_field_and_reports_success(self) -> None:
        answers = iter(
            [
                "Clean Code",
                "Robert C. Martin",
                "978-0-13-235088-4",
                "Software Engineering",
                "2",
            ]
        )
        output: list[str] = []

        book = ui_add_book(
            self.books,
            input_fn=lambda _prompt: next(answers),
            print_fn=output.append,
        )

        self.assertIsNotNone(book)
        self.assertEqual(
            output[-1],
            "Added 'Clean Code' (B001) with 2 copies.",
        )
        self.assertEqual(self.books.load()[0].isbn, "9780132350884")

    def test_reports_validation_errors(self) -> None:
        answers = iter(
            ["Clean Code", "Robert C. Martin", "not-an-isbn", "", "1"]
        )
        output: list[str] = []

        book = ui_add_book(
            self.books,
            input_fn=lambda _prompt: next(answers),
            print_fn=output.append,
        )

        self.assertIsNone(book)
        self.assertEqual(output[-1], "Error: ISBN must be 10 or 13 digits")
        self.assertEqual(self.books.load(), [])


class LibraryCommandTests(LibraryTestCase):
    def run_command(
        self, *arguments: str, stdin: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "main.py",
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

        result = self.run_command("--issue", stdin="B001\n1\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Issued 'Alpha' to Ada Lovelace. Due ", result.stdout)
        self.assertEqual(self.books.load()[0].available_copies, 0)
        self.assertEqual(len(self.loans.load()), 1)

    def test_issue_command_returns_an_error_for_invalid_choices(self) -> None:
        self.add_books(make_book())

        result = self.run_command("--issue", stdin="B999\n1\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Error:", result.stdout)
        self.assertIn("was not found", result.stdout)
        self.assertEqual(self.loans.load(), [])

    def test_return_command_returns_the_loan(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book("B001", "ada@example.com")

        result = self.run_command("--return", stdin=f"{loan.id}\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Returned 'Alpha' (loan {loan.id}).", result.stdout)
        self.assertEqual(self.books.load()[0].available_copies, 1)
        self.assertFalse(self.loans.load()[0].is_active)

    def test_return_command_reports_an_unknown_loan(self) -> None:
        self.add_books(make_book())
        self.service.issue_book("B001", "ada@example.com")

        result = self.run_command("--return", stdin="L999\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("was not found", result.stdout)

    def test_list_loans_shows_active_loans_by_default(self) -> None:
        self.add_books(
            make_book("B001", "Alpha", available_copies=1, total_copies=2),
            make_book("B002", "Beta", available_copies=1, total_copies=2),
        )
        first = self.service.issue_book("B001", "ada@example.com")
        second = self.service.issue_book("B002", "grace@example.com")
        self.service.return_book(first.id)

        result = self.run_command("--list-loans")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(second.id, result.stdout)
        self.assertNotIn(first.id, result.stdout)

    def test_list_loans_can_include_returned_loans(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book("B001", "ada@example.com")
        self.service.return_book(loan.id)

        result = self.run_command("--list-loans", "--show-returned")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(loan.id, result.stdout)
        self.assertIn("Returned", result.stdout)

    def test_overdue_command_lists_overdue_loans_with_fines(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        loan = self.service.issue_book(
            "B001",
            "ada@example.com",
            issued_on=date.today() - timedelta(days=LOAN_PERIOD_DAYS + 4),
        )

        result = self.run_command("--overdue")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(loan.id, result.stdout)
        self.assertIn("OVERDUE", result.stdout)
        self.assertIn("40", result.stdout)

    def test_overdue_command_reports_when_nothing_is_overdue(self) -> None:
        self.add_books(make_book(available_copies=1, total_copies=2))
        self.service.issue_book("B001", "ada@example.com")

        result = self.run_command("--overdue")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No overdue loans.", result.stdout)

    def test_dashboard_command_shows_counts_and_overdue_list(self) -> None:
        self.add_books(make_book())
        self.service.issue_book(
            "B001",
            "ada@example.com",
            issued_on=date.today() - timedelta(days=LOAN_PERIOD_DAYS + 2),
        )

        result = self.run_command("--dashboard")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Book titles:   1", result.stdout)
        self.assertIn("Members:       2", result.stdout)
        self.assertIn("Books on loan: 1", result.stdout)
        self.assertIn("Overdue loans: 1", result.stdout)
        self.assertIn("OVERDUE", result.stdout)

    def test_reset_command_keeps_data_when_not_confirmed(self) -> None:
        self.add_books(make_book())

        result = self.run_command("--reset", stdin="n\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Reset cancelled.", result.stdout)
        self.assertEqual(len(self.books.load()), 1)
        self.assertEqual(len(self.member_store.load()), 2)

    def test_reset_command_clears_data_when_confirmed(self) -> None:
        self.add_books(make_book())
        self.service.issue_book("B001", "ada@example.com")

        result = self.run_command("--reset", stdin="y\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Library data cleared.", result.stdout)
        self.assertEqual(self.books.load(), [])
        self.assertEqual(self.loans.load(), [])
        self.assertEqual(self.member_store.load(), [])

    def test_add_book_command_persists_a_valid_book(self) -> None:
        stdin = "\n".join(
            [
                "Clean Code",
                "Robert C. Martin",
                "978-0-13-235088-4",
                "Software Engineering",
                "2",
                "",
            ]
        )

        result = self.run_command("--add-book", stdin=stdin)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "Added 'Clean Code' (B001) with 2 copies.",
            result.stdout,
        )
        stored = self.books.load()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].isbn, "9780132350884")
        self.assertEqual(stored[0].available_copies, 2)

    def test_add_book_command_reports_an_invalid_isbn(self) -> None:
        stdin = "\n".join(
            ["Clean Code", "Robert C. Martin", "12345", "General", "1", ""]
        )

        result = self.run_command("--add-book", stdin=stdin)

        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: ISBN must be 10 or 13 digits", result.stdout)
        self.assertEqual(self.books.load(), [])


if __name__ == "__main__":
    unittest.main()
