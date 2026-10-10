"""Market-data refresh job: reference lists → prices (holdings + benchmarks) → NAVs.

Each step skips anything that is already fresh unless `force` is set, so the job is cheap to
run often. A failure on one item is recorded and the job moves on; old data is kept.
"""

from collections.abc import Callable
from functools import partial
from typing import Literal, get_args

from sqlmodel import Session

from app.core.db import get_engine
from app.core.profiles import ReferenceKey
from app.data.delivery import refresh_delivery
from app.data.files import REFERENCE_FILES
from app.data.navs import refresh_nav
from app.data.prices import refresh_daily
from app.data.quotes import benchmark_targets, fund_targets, stock_targets
from app.data.reference_refresh import refresh_reference
from app.data.store import RefreshResult
from app.jobs.runner import JobFn, Progress

Scope = Literal["all", "reference", "prices", "navs"]
SCOPES: tuple[Scope, ...] = get_args(Scope)
JOB_KIND = "market_refresh"


def market_refresh(scope: Scope = "all", force: bool = False) -> JobFn:
    def run(progress: Progress) -> str:
        with Session(get_engine()) as s:
            steps: list[tuple[str, Callable[[], RefreshResult]]] = []
            # The AMFI list carries the day's NAVs, so the NAV refresh updates it too.
            ref_keys: list[ReferenceKey] = []
            if scope in ("all", "reference"):
                ref_keys = list(REFERENCE_FILES)
            elif scope == "navs":
                ref_keys = ["amfi_navall"]
            for key in ref_keys:
                steps.append(
                    (REFERENCE_FILES[key].label, partial(refresh_reference, s, key, force=force))
                )
            if scope in ("all", "prices"):
                for t in benchmark_targets() + stock_targets(s):
                    steps.append((t.label, partial(refresh_daily, s, t.code, t.label, force=force)))
            if scope in ("all", "prices"):
                steps.append(("NSE delivery data", partial(refresh_delivery, s, force=force)))
            if scope in ("all", "navs"):
                for t in fund_targets(s):
                    steps.append((t.label, partial(refresh_nav, s, t.code, t.label, force=force)))

            counts = {"updated": 0, "skipped": 0, "failed": 0}
            total = len(steps)
            progress.update(0, total, "Starting")
            for i, (label, step) in enumerate(steps):
                progress.update(i, total, f"Refreshing {label}")
                try:
                    result = step()
                    # Never leave a transaction open between steps: progress updates use their
                    # own connection, and SQLite allows one writer at a time.
                    s.commit()
                except Exception as e:  # unexpected bug: record it, keep going
                    s.rollback()
                    result = RefreshResult("?", label, "failed", f"{e.__class__.__name__}: {e}")
                counts[result.outcome] += 1
                if result.outcome == "failed":
                    progress.error(f"{label}: {result.message}")
            progress.update(total, total)
        return (
            f"{counts['updated']} updated, {counts['skipped']} already fresh, "
            f"{counts['failed']} failed"
        )

    return run
