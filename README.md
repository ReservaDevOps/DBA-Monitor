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
- `data`: snapshots leves de status, ignorados pelo Git.
- `reports`: saída dos relatórios, ignorada pelo Git.
- `environment`: credenciais, perfis `.ovpn`, certificados e arquivos `.env`,
  sempre ignorados pelo Git.

## Exemplo Client A

Os arquivos sensíveis ficam em:

```text
environment/vpn/client-a/
environment/db/client-a.env
```

O OpenVPN deve estar em `environment/vpn/client-a/client.ovpn`.

Subir VPN e agente:

```bash
docker compose up --build vpn-client-a agent-client-a
```

API local:

```bash
curl http://127.0.0.1:18081/health
curl http://127.0.0.1:18081/status
curl http://127.0.0.1:18081/reports
```

Gerar relatório diário sob demanda:

```bash
curl -X POST http://127.0.0.1:18081/reports/run-now
```

Checar o túnel manualmente:

```bash
docker compose exec vpn-client-a ip addr show tun0
docker compose exec vpn-client-a ip route
```

## Jobs

O agente roda dois jobs internos:

- status leve a cada `STATUS_INTERVAL_SECONDS` segundos;
- relatório diário no horário `DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE`.

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
  estiver habilitado no database monitorado.

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
- revise o histórico com `git log -p --all` antes do primeiro push público.

Evite rodar `docker compose config` em logs compartilhados depois de criar
arquivos reais em `environment/`, porque o Compose expande variáveis de
`env_file` na saída.
