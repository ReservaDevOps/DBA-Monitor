from datetime import datetime, timezone

from app.db import connection_info, fetch_all, fetch_one


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
        "database_size": database_size,
    }

