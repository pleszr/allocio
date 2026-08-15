"""One-off data fix: flag Focus Kombi's June/September 2025 catch-up expenses `excluded_from_average`.

Run once, from `backend/`, as a module so `app.*` resolves:

    cd backend && uv run python -m scripts.migrate_focus_kombi_exclude_catchup

Applies the new per-expense `excluded_from_average` feature (issue: the dashboard's trailing-average
KPIs were skewed by two known, anticipated one-time costs -- the June 2025 acquisition-date setup
and the September 2025 post-purchase catch-up service) to the asset already posted by
`import_focus_kombi.py` in a running environment, without re-importing it from scratch.

Goes through the normal `CheckInService.edit_check_in` path -- the same "Check-in expense edit
(deliberate exception)" workflow the History tab's edit UI uses -- rather than a raw SQL UPDATE, so
the change is exercised through real application code (dogfooding the new edit-time
`excluded_from_average` support) and stays subject to its usual guards (forward-simulation balance
check, owned-check-in lookup). Each edited check-in's expense lines are resubmitted unchanged except
for the new flag; `paid_out_of_pocket_override` is set to each line's current stored split so the
edit reproduces the exact same amounts (matching how the frontend's own edit form seeds and re-saves
a posted check-in, per `CheckInScreen.tsx`'s `draftsFromExpenseLines`).

Idempotent: re-running it is a no-op resubmit of already-flagged lines.
"""

from datetime import date

from app.db import SessionLocal
from app.domain.asset import Asset
from app.domain.user import User
from app.repository import check_in_repository
from app.services.check_in_service import CheckInService, ExpenseDraft

OWNER_EMAIL = "plesz.roland@gmail.com"
ASSET_NAME = "Focus Kombi"
TARGET_PERIOD_ENDS = [date(2025, 6, 25), date(2025, 9, 1)]


def main() -> None:
    """Re-edit the two catch-up check-ins so every one of their expense lines is excluded_from_average."""
    session = SessionLocal()
    try:
        owner = session.query(User).filter_by(email=OWNER_EMAIL).one()
        check_in_service = CheckInService(session)

        asset = _find_asset(session, owner.id)
        check_ins = {
            check_in.period_end: check_in
            for check_in in check_in_repository.list_posted_check_ins(session, asset.id)
            if check_in.period_end in TARGET_PERIOD_ENDS
        }
        missing = [period_end for period_end in TARGET_PERIOD_ENDS if period_end not in check_ins]
        if missing:
            raise RuntimeError(f"Expected posted check-ins for {missing}, not found under asset {asset.id}")

        for period_end in TARGET_PERIOD_ENDS:
            check_in = check_ins[period_end]
            detail = check_in_service.get_check_in_detail(owner.id, asset.id, check_in.id)
            drafts = [
                ExpenseDraft(
                    kind=line.kind,
                    amount=line.amount,
                    event_date=line.event_date,
                    usage_counter_at_event=line.usage_counter_at_event,
                    comment=line.comment,
                    source_type=line.source_type,
                    source_id=line.source_id,
                    paid_out_of_pocket_override=line.paid_out_of_pocket,
                    excluded_from_average=True,
                )
                for line in detail.expense_lines
            ]
            _, expense_events = check_in_service.edit_check_in(
                owner.id, asset.id, check_in.id, drafts, detail.notes
            )
            print(
                f"Re-flagged {len(expense_events)} expense line(s) on check-in {check_in.id} "
                f"({period_end.isoformat()}) as excluded_from_average"
            )

        session.commit()
        print("\nDone.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _find_asset(session, owner_id):  # noqa: ANN001, ANN201 - Session/Asset, kept loosely typed for this script
    """Look up the Focus Kombi asset by name under the owning user."""
    return session.query(Asset).filter_by(user_id=owner_id, name=ASSET_NAME).one()


if __name__ == "__main__":
    main()
