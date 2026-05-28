#!/usr/bin/env bash
set -euo pipefail

report_name="${REPORT_NAME:-report}"
timestamp="$(date +%Y%m%d-%H%M%S)"
output="/reports/${report_name}-${timestamp}.csv"

mkdir -p /reports

psql \
  --set=ON_ERROR_STOP=1 \
  --csv \
  --file=/queries/sample-report.sql \
  --output="$output"

echo "Report written to $output"

