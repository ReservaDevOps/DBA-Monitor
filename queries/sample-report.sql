\pset footer off

select
  now() as collected_at,
  current_database() as database_name,
  current_user as database_user,
  inet_server_addr() as server_addr,
  inet_server_port() as server_port,
  version() as postgres_version;

