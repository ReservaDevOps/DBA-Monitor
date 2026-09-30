# DBA Monitor

Agente de monitoramento PostgreSQL por VPN isolada.

Cada VPN roda em um container próprio. O agente usa `network_mode:
"service:<vpn>"`, então ele compartilha a rede da VPN sem alterar as rotas da
máquina host. Isso permite rodar múltiplas VPNs simultâneas, cada uma com seu
agente e sua própria visão de rede.

## Estrutura

- `docker/vpn`: imagem OpenVPN genérica.
- `docker/agent`: imagem baseada em PostgreSQL 16 com FastAPI, APScheduler e
  `psql`.
- `app`: API, scheduler, coletores e gerador de relatórios.
- `os_collector`: coletor local Linux que grava métricas de SO no PostgreSQL.
- `sql`: schemas auxiliares versionados.
- `data`: snapshots leves de status, ignorados pelo Git.
- `reports`: saída dos relatórios, ignorada pelo Git.
- `environment`: credenciais, perfis `.ovpn`, certificados e arquivos `.env`,
  sempre ignorados pelo Git.
- `environment/evolution`: configuração real local da Evolution API e snapshot
  de bootstrap da sessão WhatsApp, sempre ignorados pelo Git.

## Exemplo Client A

Os arquivos sensíveis ficam em:

```text
environment/vpn/client-a/
environment/db/client-a.env
```

O OpenVPN deve estar em `environment/vpn/client-a/client.ovpn`.

Subir VPN e agente:

```bash
docker compose up --build dba-evolution-api vpn-client-a agent-client-a
```

Por padrão, o Compose publica a API somente no `127.0.0.1` do host e exige
`AGENT_API_TOKEN` no arquivo `environment/db/client-a.env`. Envie o header
`x-api-token` nas chamadas protegidas.

API local:

```bash
curl http://127.0.0.1:18081/health
curl -H "x-api-token: $AGENT_API_TOKEN" http://127.0.0.1:18081/status
curl -H "x-api-token: $AGENT_API_TOKEN" http://127.0.0.1:18081/reports
```

Gerar relatório diário sob demanda:

```bash
curl -X POST -H "x-api-token: $AGENT_API_TOKEN" http://127.0.0.1:18081/reports/run-now
```

## Evolution API e WhatsApp

O Compose sobe uma Evolution API própria do projeto para envio dos relatórios
por WhatsApp:

```text
dba-evolution-api         http://127.0.0.1:18080
dba-evolution-postgres    dados da Evolution
dba-evolution-redis       cache da Evolution
```

Os agentes acessam a Evolution pela rede Docker interna:

```text
EVOLUTION_API_URL=http://dba-evolution-api:8080
```

Configure os valores reais em `environment/db/<client>.env`:

```text
EVOLUTION_ENABLED=true
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE=Reserva Whats
EVOLUTION_TARGET_GROUP_JID=120000000000000000@g.us
EVOLUTION_SEND_PDF=true
```

O envio acontece após a geração do relatório. Se o WhatsApp falhar, o relatório
continua sendo gerado; a falha fica registrada no log do agente.

Para listar grupos disponíveis na instância conectada:

```bash
curl -H "apikey: $EVOLUTION_API_KEY" \
  "http://127.0.0.1:18080/group/fetchAllGroups/Reserva%20Whats?getParticipants=false"
```

## Multicliente

`client-a` sobe por padrão na porta local `18081`.

Para subir também o `client-b`, crie os arquivos reais:

```text
environment/db/client-b.env
environment/vpn/client-b/client.ovpn
```

Depois execute:

```bash
docker compose --profile client-b up --build \
  dba-evolution-api vpn-client-a agent-client-a vpn-client-b agent-client-b
```

O `client-b` publica a API local em `127.0.0.1:18082`.

Checar o túnel manualmente:

```bash
docker compose exec vpn-client-a ip addr show tun0
docker compose exec vpn-client-a ip route
```

## Jobs

O agente roda dois jobs internos:

- status leve a cada `STATUS_INTERVAL_SECONDS` segundos;
- relatório diário no horário `DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE`.

O status leve pode enviar warnings pelo WhatsApp quando
`STATUS_WARNINGS_ENABLED=true`. Thresholds vazios ficam desativados:

- `STATUS_WARNING_MAX_CONNECTIONS`;
- `STATUS_WARNING_MAX_CONNECTIONS_PERCENT`, calculado sobre `max_connections`;
- `STATUS_WARNING_MAX_LONG_QUERIES`;
- `STATUS_WARNING_MAX_WAITING_LOCKS`;
- `STATUS_WARNING_MAX_DATABASE_SIZE_GB`;
- `STATUS_WARNING_COOLDOWN_SECONDS`, para evitar repetição contínua do mesmo
  alerta.

O status também registra `server_settings.max_connections` e tamanhos de
tablespaces. Quando `OS_METRICS_ENABLED=true`, também consulta as views do
schema `dba_monitor` populadas pelo coletor local de SO.

## Métricas locais de SO

O coletor em `os_collector/dba_os_collector` roda no servidor Linux monitorado
e grava amostras no PostgreSQL. Ele coleta load average, CPU por delta de
`/proc/stat`, memória/swap por `/proc/meminfo`, contagem de processos e uso de
filesystems por `/proc/mounts` + `statvfs`. Disk I/O ainda não faz parte desta
primeira fase.

Crie o schema no PostgreSQL monitorado:

```bash
psql -h <host> -U <admin-ou-owner> -d <database> -f sql/os_metrics_schema.sql
```

Use um usuário com permissão de `insert/select/delete` no schema
`dba_monitor` para o coletor. O agente do DBA Monitor só precisa de `select`
nas views `dba_monitor.os_metric_latest` e
`dba_monitor.os_filesystem_latest`.

Exemplo de teste local:

```bash
python3 -m venv /opt/dba-monitor/venv
/opt/dba-monitor/venv/bin/pip install "psycopg[binary]"
cp environment.example/os-collector.env.example /etc/dba-monitor/os-collector.env
set -a
. /etc/dba-monitor/os-collector.env
set +a
PYTHONPATH=/opt/dba-monitor/os_collector \
  /opt/dba-monitor/venv/bin/python -m dba_os_collector --once
```

O unit file de referência está em
`packaging/systemd/dba-os-collector.service`. Ajuste `User`,
`WorkingDirectory`, `EnvironmentFile` e o caminho do Python conforme a instalação
real antes de habilitar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dba-os-collector
```

No `.env` do agente, habilite a consulta e os thresholds desejados:

```text
OS_METRICS_ENABLED=true
OS_WARNING_MAX_FILESYSTEM_USED_PERCENT=90
OS_WARNING_MAX_MEMORY_USED_PERCENT=90
OS_WARNING_MAX_IOWAIT_PERCENT=20
OS_WARNING_MAX_COLLECTOR_LAG_SECONDS=180
```

Se o schema, as tabelas ou permissões ainda não existirem, o snapshot de status
mantém o bloco `os_metrics` como `unavailable` com um erro curto, sem derrubar o
status geral.

O relatório diário gera:

- CSVs por dataset;
- `summary.html` em português;
- `summary.pdf` em português, em paisagem.

Datasets incluídos:

- identificação da instância;
- tamanhos de databases;
- maiores tabelas em todos os databases acessíveis;
- conexões por usuário/aplicação/estado;
- queries em execução há mais de 5 minutos;
- locks;
- saúde de vacuum/analyze em todos os databases acessíveis;
- status da varredura multi-database, incluindo databases sem permissão de
  conexão quando houver;
- top SQLs por tempo total, tempo médio e I/O quando `pg_stat_statements`
  estiver habilitado nos databases acessíveis.

Use `MAX_DATABASES_PER_REPORT` para limitar a quantidade de bancos varridos por
execução. O valor `0` mantém a varredura sem limite.

Endpoints principais:

```text
GET  /health
GET  /status
GET  /metrics/latest
GET  /reports
POST /reports/run-now
GET  /reports/{report_name}/{date}/html
GET  /reports/{report_name}/{date}/pdf
```

## Publicação

Antes de publicar este repositório:

- mantenha arquivos reais somente em `environment/`;
- não versione `.ovpn`, certificados, chaves privadas, `.env`, `.pgpass` ou
  bancos KeePass;
- não salve relatórios reais em Git;
- não versione `environment/evolution/evolution.env` nem dumps de bootstrap da
  Evolution API;
- não publique a API em `0.0.0.0` sem autenticação ou firewall;
- revise o histórico com `git log -p --all` antes do primeiro push público.

Evite rodar `docker compose config` em logs compartilhados depois de criar
arquivos reais em `environment/`, porque o Compose expande variáveis de
`env_file` na saída.
