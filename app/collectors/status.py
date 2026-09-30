from datetime import datetime, timezone
import logging

from app.collectors.os_metrics import collect_os_metrics
from app.db import connection_info, fetch_all, fetch_one


logger = logging.getLogger(__name__)


def _optional_fetch_one(sql: str) -> dict | None:
    try:
        return fetch_one(sql)
    except Exception as exc:
        logger.warning("Optional status query failed: %s", exc)
        return None


def _optional_fetch_all(sql: str) -> list[dict]:
    try:
        return fetch_all(sql)
    except Exception as exc:
        logger.warning("Optional status query failed: %s", exc)
        return []


def collect_status() -> dict:
    instance = fetch_one(
        """
        select
          now() as collected_at,
          current_database() as database_name,
          current_user as database_user,
          inet_server_addr()::text as server_addr,
          inet_server_port() as server_port,
          version() as postgres_version,
          pg_postmaster_start_time() as postmaster_start_time
        """
    )

    activity = fetch_all(
        """
        select
          state,
          count(*)::int as sessions
        from pg_stat_activity
        group by state
        order by state nulls first
        """
    )

    long_queries = fetch_all(
        """
        select
          pid,
          usename,
          datname,
          state,
          now() - query_start as duration,
          left(regexp_replace(query, '\\s+', ' ', 'g'), 300) as query
        from pg_stat_activity
        where query_start is not null
          and now() - query_start > interval '5 minutes'
          and state <> 'idle'
        order by query_start
        limit 20
        """
    )

    locks = fetch_one(
        """
        select
          count(*) filter (where not granted)::int as waiting_locks,
          count(*)::int as total_locks
        from pg_locks
        """
    )

    server_settings = _optional_fetch_one(
        """
        select
          current_setting('max_connections')::int as max_connections
        """
    ) or {}

    data_directory = _optional_fetch_one(
        """
        select current_setting('data_directory', true) as data_directory
        """
    )
    if data_directory:
        server_settings["data_directory"] = data_directory.get("data_directory")

    tablespaces = _optional_fetch_all(
        """
        select
          spcname,
          pg_tablespace_location(oid) as location,
          pg_tablespace_size(oid) as bytes,
          pg_size_pretty(pg_tablespace_size(oid)) as pretty
        from pg_tablespace
        order by spcname
        """
    )

    database_size = fetch_one(
        """
        select
          pg_database_size(current_database()) as bytes,
          pg_size_pretty(pg_database_size(current_database())) as pretty
        """
    )

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "connection": connection_info(),
        "instance": instance,
        "activity": activity,
        "long_queries": long_queries,
        "locks": locks,
        "server_settings": server_settings,
        "tablespaces": tablespaces,
        "database_size": database_size,
        "os_metrics": collect_os_metrics(),
    }
