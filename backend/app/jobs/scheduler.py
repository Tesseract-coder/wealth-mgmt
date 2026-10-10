"""Daily refresh schedule (APScheduler, Asia/Kolkata). Missed runs coalesce into one."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.profiles import get_profiles, parse_hhmm
from app.jobs.runner import JobRunner
from app.jobs.tasks import FUND_JOB_KIND, JOB_KIND, fundamentals_refresh, market_refresh

logger = logging.getLogger(__name__)
TZ = "Asia/Kolkata"


def start_scheduler(runner: JobRunner) -> BackgroundScheduler:
    cfg = get_profiles().data
    sched = BackgroundScheduler(timezone=TZ)
    price_t, nav_t = parse_hhmm(cfg.refresh_time_ist), parse_hhmm(cfg.nav_refresh_time_ist)
    sched.add_job(
        lambda: runner.submit(
            JOB_KIND,
            market_refresh("all", sheets=True),
            params={"scope": "all", "sheets": True},
            trigger="schedule",
        ),
        CronTrigger(day_of_week="mon-fri", hour=price_t.hour, minute=price_t.minute, timezone=TZ),
        id="prices",
        name="Daily price refresh",
        coalesce=True,
        misfire_grace_time=3600,
    )
    sched.add_job(
        lambda: runner.submit(
            JOB_KIND, market_refresh("navs"), params={"scope": "navs"}, trigger="schedule"
        ),
        CronTrigger(hour=nav_t.hour, minute=nav_t.minute, timezone=TZ),
        id="navs",
        name="Daily NAV refresh",
        coalesce=True,
        misfire_grace_time=3600,
    )
    fcfg = get_profiles().fundamental
    fund_t = parse_hhmm(fcfg.refresh_time_ist)
    sched.add_job(
        lambda: runner.submit(
            FUND_JOB_KIND, fundamentals_refresh(), params={"peers": True}, trigger="schedule"
        ),
        CronTrigger(
            day_of_week=fcfg.refresh_day, hour=fund_t.hour, minute=fund_t.minute, timezone=TZ
        ),
        id="fundamentals",
        name="Weekly fundamentals refresh",
        coalesce=True,
        misfire_grace_time=6 * 3600,
    )
    sched.start()
    logger.info(
        "Scheduler started: prices Mon–Fri %s IST, NAVs daily %s IST",
        cfg.refresh_time_ist,
        cfg.nav_refresh_time_ist,
    )
    return sched
