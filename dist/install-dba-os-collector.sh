#!/usr/bin/env bash
set -euo pipefail

DEFAULT_BASE_URL="https://files-ibr-desmonte.s3.amazonaws.com/dba-monitor"
BASE_URL="${DBA_MONITOR_INSTALL_BASE_URL:-$DEFAULT_BASE_URL}"
INSTALL_DIR="${DBA_MONITOR_INSTALL_DIR:-/opt/dba-monitor}"
CONFIG_DIR="${DBA_MONITOR_CONFIG_DIR:-/etc/dba-monitor}"
SERVICE_FILE="/etc/systemd/system/dba-os-collector.service"
SERVICE_USER="${DBA_MONITOR_SERVICE_USER:-dba-monitor}"
SERVICE_GROUP="${DBA_MONITOR_SERVICE_GROUP:-dba-monitor}"
ARCHIVE_URL="${BASE_URL%/}/os_collector.tar.gz"
SERVICE_URL="${BASE_URL%/}/dba-os-collector.service"
SCHEMA_URL="${BASE_URL%/}/os_metrics_schema.sql"

log() {
  printf '[dba-os-collector] %s\n' "$*"
}

die() {
  printf '[dba-os-collector] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    die "execute como root: curl -fsSL ${BASE_URL%/}/install-dba-os-collector.sh | sudo bash"
  fi
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "comando obrigatorio nao encontrado: $1"
}

prompt_default() {
  local var_name="$1"
  local label="$2"
  local default_value="$3"
  local value
  read -r -p "${label} [${default_value}]: " value </dev/tty
  printf -v "$var_name" '%s' "${value:-$default_value}"
}

prompt_secret() {
  local var_name="$1"
  local label="$2"
  local value
  read -r -s -p "${label}: " value </dev/tty
  printf '\n'
  [ -n "$value" ] || die "${label} nao pode ficar vazio"
  printf -v "$var_name" '%s' "$value"
}

prompt_yes_no() {
  local var_name="$1"
  local label="$2"
  local default_value="$3"
  local value suffix
  if [ "$default_value" = "yes" ]; then
    suffix="S/n"
  else
    suffix="s/N"
  fi
  read -r -p "${label} [${suffix}]: " value </dev/tty
  value="${value:-$default_value}"
  case "${value,,}" in
    s|sim|y|yes) printf -v "$var_name" '%s' "yes" ;;
    n|nao|não|no) printf -v "$var_name" '%s' "no" ;;
    *) die "resposta invalida para ${label}" ;;
  esac
}

shell_quote() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\\\'\'}"
}

sql_literal() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\'}"
}

sql_ident() {
  local value="$1"
  printf '"%s"' "${value//\"/\"\"}"
}

write_env_var() {
  local name="$1"
  local value="$2"
  printf '%s=%s\n' "$name" "$(shell_quote "$value")"
}

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
      ca-certificates curl python3 python3-venv python3-pip tar
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl python3 python3-pip tar \
      || dnf --disablerepo='pgdg*' install -y ca-certificates curl python3 python3-pip tar
    return
  fi

  if command -v yum >/dev/null 2>&1; then
    yum install -y ca-certificates curl python3 python3-pip tar \
      || yum --disablerepo='pgdg*' install -y ca-certificates curl python3 python3-pip tar
    return
  fi

  die "gerenciador de pacotes nao suportado; instale curl, python3, venv/pip e tar manualmente"
}

ensure_user() {
  if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
    groupadd --system "$SERVICE_GROUP"
  fi
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --gid "$SERVICE_GROUP" --home-dir "$INSTALL_DIR" \
      --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
}

write_config() {
  local config_file="${CONFIG_DIR}/os-collector.env"
  if [ -f "$config_file" ]; then
    prompt_yes_no OVERWRITE_CONFIG "Arquivo ${config_file} ja existe. Sobrescrever" "no"
    if [ "$OVERWRITE_CONFIG" = "no" ]; then
      log "mantendo configuracao existente"
      return
    fi
  fi

  install -d -m 0750 "$CONFIG_DIR"
  local previous_umask
  previous_umask="$(umask)"
  umask 077
  {
    write_env_var PGHOST "$PGHOST_VALUE"
    write_env_var PGPORT "$PGPORT_VALUE"
    write_env_var PGDATABASE "$PGDATABASE_VALUE"
    write_env_var PGUSER "$PGUSER_VALUE"
    write_env_var PGPASSWORD "$PGPASSWORD_VALUE"
    write_env_var PGSSLMODE "$PGSSLMODE_VALUE"
    printf '\n'
    write_env_var OS_COLLECTOR_DSN ""
    write_env_var OS_COLLECTOR_HOST_ID "$HOST_ID_VALUE"
    write_env_var OS_COLLECTOR_POSTGRES_DATA_DIRECTORY "$PGDATA_VALUE"
    write_env_var OS_COLLECTOR_INTERVAL_SECONDS "$INTERVAL_VALUE"
    write_env_var OS_COLLECTOR_RETENTION_DAYS "$RETENTION_VALUE"
    write_env_var OS_COLLECTOR_CPU_SAMPLE_SECONDS "1"
    write_env_var OS_COLLECTOR_LOG_LEVEL "INFO"
  } > "$config_file"
  umask "$previous_umask"
  chown root:"$SERVICE_GROUP" "$config_file"
  chmod 0640 "$config_file"
}

install_collector() {
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  install -d -m 0755 "$INSTALL_DIR"
  log "baixando pacote do coletor"
  curl -fsSL "$ARCHIVE_URL" -o "${tmp_dir}/os_collector.tar.gz"
  tar -xzf "${tmp_dir}/os_collector.tar.gz" -C "$INSTALL_DIR"

  log "criando virtualenv"
  python3 -m venv "${INSTALL_DIR}/venv"
  "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip >/dev/null
  "${INSTALL_DIR}/venv/bin/pip" install "psycopg[binary]"

  chown -R root:root "$INSTALL_DIR"
  chmod 0755 "$INSTALL_DIR"
  chmod -R a+rX "${INSTALL_DIR}/venv"
  find "$INSTALL_DIR/os_collector" -type d -exec chmod 0755 {} \;
  find "$INSTALL_DIR/os_collector" -type f -exec chmod 0644 {} \;
  rm -rf "$tmp_dir"
}

install_service() {
  local tmp_service
  tmp_service="$(mktemp)"
  curl -fsSL "$SERVICE_URL" -o "$tmp_service"
  install -m 0644 "$tmp_service" "$SERVICE_FILE"
  rm -f "$tmp_service"
  systemctl daemon-reload
}

apply_schema_and_grants() {
  local schema_file sql_file
  schema_file="$(mktemp)"
  sql_file="$(mktemp)"
  curl -fsSL "$SCHEMA_URL" -o "$schema_file"

  cat "$schema_file" > "$sql_file"
  {
    printf '\n'
    printf 'do $$\n'
    printf 'begin\n'
    printf '  if not exists (select 1 from pg_roles where rolname = %s) then\n' "$(sql_literal "$PGUSER_VALUE")"
    printf "    execute format('create role %%I login password %%L', %s, %s);\n" "$(sql_literal "$PGUSER_VALUE")" "$(sql_literal "$PGPASSWORD_VALUE")"
    printf '  end if;\n'
    printf 'end $$;\n'
    printf 'grant usage on schema dba_monitor to %s;\n' "$(sql_ident "$PGUSER_VALUE")"
    printf 'grant select, insert, update on dba_monitor.host to %s;\n' "$(sql_ident "$PGUSER_VALUE")"
    printf 'grant insert, delete on dba_monitor.os_metric_sample to %s;\n' "$(sql_ident "$PGUSER_VALUE")"
    printf 'grant insert, delete on dba_monitor.os_filesystem_sample to %s;\n' "$(sql_ident "$PGUSER_VALUE")"
    printf 'grant select on dba_monitor.os_metric_latest to %s;\n' "$(sql_ident "$PGUSER_VALUE")"
    printf 'grant select on dba_monitor.os_filesystem_latest to %s;\n' "$(sql_ident "$PGUSER_VALUE")"
  } >> "$sql_file"
  chmod 0644 "$sql_file"

  if command -v sudo >/dev/null 2>&1; then
    (cd /tmp && sudo -u postgres psql -d "$PGDATABASE_VALUE" -v ON_ERROR_STOP=1 -f "$sql_file")
  else
    su - postgres -c "cd /tmp && psql -d $(shell_quote "$PGDATABASE_VALUE") -v ON_ERROR_STOP=1 -f $(shell_quote "$sql_file")"
  fi

  rm -f "$schema_file" "$sql_file"
}

test_collector() {
  log "executando coleta de teste"
  set -a
  # shellcheck disable=SC1091
  . "${CONFIG_DIR}/os-collector.env"
  set +a
  PYTHONPATH="${INSTALL_DIR}/os_collector" \
    "${INSTALL_DIR}/venv/bin/python" -m dba_os_collector --once
}

main() {
  require_root
  need_command curl
  need_command tar
  need_command systemctl

  log "instalador do DBA OS Collector"
  prompt_default PGHOST_VALUE "PostgreSQL host" "127.0.0.1"
  prompt_default PGPORT_VALUE "PostgreSQL port" "5432"
  prompt_default PGDATABASE_VALUE "PostgreSQL database" "postgres"
  prompt_default PGUSER_VALUE "Usuario do coletor" "dba_monitor_collector"
  prompt_secret PGPASSWORD_VALUE "Senha do usuario do coletor"
  prompt_default PGSSLMODE_VALUE "PGSSLMODE" "disable"
  prompt_default HOST_ID_VALUE "Host ID do coletor" "$(hostname -s 2>/dev/null || hostname)"
  prompt_default PGDATA_VALUE "Diretorio de dados do PostgreSQL" "/var/lib/pgsql/16/data"
  prompt_default INTERVAL_VALUE "Intervalo de coleta em segundos" "60"
  prompt_default RETENTION_VALUE "Retencao em dias" "30"
  prompt_yes_no APPLY_SCHEMA "Aplicar schema e grants via usuario local postgres" "yes"

  install_packages
  ensure_user
  write_config
  install_collector
  install_service

  if [ "$APPLY_SCHEMA" = "yes" ]; then
    apply_schema_and_grants
  else
    log "schema/grants nao aplicados; faca isso antes de iniciar o servico"
  fi

  test_collector
  systemctl enable --now dba-os-collector
  systemctl --no-pager --full status dba-os-collector || true

  log "instalacao concluida"
  log "logs: journalctl -u dba-os-collector -f"
}

main "$@"
