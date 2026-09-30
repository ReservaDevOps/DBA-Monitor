-- DBA Monitor OS metrics schema for PostgreSQL 12+.
-- Apply this file on the monitored PostgreSQL instance before running
-- the local Linux collector. It intentionally contains no credentials.

create schema if not exists dba_monitor;

create table if not exists dba_monitor.host (
    host_id text primary key,
    hostname text not null,
    os_name text,
    kernel_release text,
    postgres_data_directory text,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

comment on table dba_monitor.host is
    'Linux hosts that publish local OS metrics for DBA Monitor.';
comment on column dba_monitor.host.host_id is
    'Stable collector host identifier. Prefer OS_COLLECTOR_HOST_ID in production.';
comment on column dba_monitor.host.postgres_data_directory is
    'Optional PostgreSQL data directory path as seen by the Linux host.';

create table if not exists dba_monitor.os_metric_sample (
    host_id text not null references dba_monitor.host(host_id) on delete cascade,
    collected_at timestamptz not null,
    load1 numeric,
    load5 numeric,
    load15 numeric,
    cpu_user_percent numeric(6,2),
    cpu_system_percent numeric(6,2),
    cpu_idle_percent numeric(6,2),
    cpu_iowait_percent numeric(6,2),
    cpu_irq_percent numeric(6,2),
    cpu_softirq_percent numeric(6,2),
    cpu_steal_percent numeric(6,2),
    memory_total_bytes bigint,
    memory_available_bytes bigint,
    memory_used_percent numeric(6,2),
    swap_total_bytes bigint,
    swap_free_bytes bigint,
    swap_used_percent numeric(6,2),
    process_count integer,
    primary key (host_id, collected_at)
);

comment on table dba_monitor.os_metric_sample is
    'Point-in-time Linux load, CPU, memory, swap and process count samples.';
comment on column dba_monitor.os_metric_sample.cpu_iowait_percent is
    'CPU iowait percentage calculated from /proc/stat delta between samples.';
comment on column dba_monitor.os_metric_sample.memory_used_percent is
    'Calculated as (MemTotal - MemAvailable) / MemTotal.';

create table if not exists dba_monitor.os_filesystem_sample (
    host_id text not null references dba_monitor.host(host_id) on delete cascade,
    collected_at timestamptz not null,
    mount_point text not null,
    device text,
    filesystem_type text,
    total_bytes bigint,
    used_bytes bigint,
    free_bytes bigint,
    available_bytes bigint,
    used_percent numeric(6,2),
    primary key (host_id, collected_at, mount_point)
);

comment on table dba_monitor.os_filesystem_sample is
    'Point-in-time Linux filesystem capacity samples from /proc/mounts and statvfs.';
comment on column dba_monitor.os_filesystem_sample.used_percent is
    'Calculated against blocks available to non-root users when available.';

create index if not exists os_metric_sample_collected_at_idx
    on dba_monitor.os_metric_sample (collected_at desc);

create index if not exists os_metric_sample_host_collected_at_idx
    on dba_monitor.os_metric_sample (host_id, collected_at desc);

create index if not exists os_filesystem_sample_collected_at_idx
    on dba_monitor.os_filesystem_sample (collected_at desc);

create index if not exists os_filesystem_sample_host_collected_at_idx
    on dba_monitor.os_filesystem_sample (host_id, collected_at desc);

create index if not exists os_filesystem_sample_mount_point_idx
    on dba_monitor.os_filesystem_sample (mount_point);

create or replace view dba_monitor.os_metric_latest as
select
    h.host_id,
    h.hostname,
    h.os_name,
    h.kernel_release,
    h.postgres_data_directory,
    s.collected_at,
    extract(epoch from (now() - s.collected_at))::bigint as collector_lag_seconds,
    s.load1,
    s.load5,
    s.load15,
    s.cpu_user_percent,
    s.cpu_system_percent,
    s.cpu_idle_percent,
    s.cpu_iowait_percent,
    s.cpu_irq_percent,
    s.cpu_softirq_percent,
    s.cpu_steal_percent,
    s.memory_total_bytes,
    s.memory_available_bytes,
    s.memory_used_percent,
    s.swap_total_bytes,
    s.swap_free_bytes,
    s.swap_used_percent,
    s.process_count
from dba_monitor.host h
join lateral (
    select *
    from dba_monitor.os_metric_sample s
    where s.host_id = h.host_id
    order by s.collected_at desc
    limit 1
) s on true;

comment on view dba_monitor.os_metric_latest is
    'Latest OS metric sample per host, with collector lag in seconds.';

create or replace view dba_monitor.os_filesystem_latest as
with latest_sample as (
    select host_id, max(collected_at) as collected_at
    from dba_monitor.os_metric_sample
    group by host_id
)
select
    h.host_id,
    h.hostname,
    f.collected_at,
    extract(epoch from (now() - f.collected_at))::bigint as collector_lag_seconds,
    f.mount_point,
    f.device,
    f.filesystem_type,
    f.total_bytes,
    f.used_bytes,
    f.free_bytes,
    f.available_bytes,
    f.used_percent
from dba_monitor.host h
join latest_sample ls on ls.host_id = h.host_id
join dba_monitor.os_filesystem_sample f on f.host_id = h.host_id
    and f.collected_at = ls.collected_at
order by h.host_id, f.mount_point;

comment on view dba_monitor.os_filesystem_latest is
    'Filesystem samples from the latest host collection only, avoiding stale mounts.';
