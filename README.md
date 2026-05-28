# DBA Monitor

Projeto de laboratório para executar monitores PostgreSQL por VPN isolada.

Cada VPN roda em um container próprio. O worker de relatório usa `network_mode:
"service:<vpn>"`, então ele compartilha a rede da VPN sem alterar as rotas da
máquina host.

## Estrutura

- `docker/vpn`: imagem OpenVPN genérica.
- `docker/monitor`: imagem baseada em PostgreSQL 16 com `psql`.
- `queries`: consultas versionadas.
- `scripts`: scripts versionados.
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

Subir só a VPN:

```bash
docker compose up --build vpn-client-a
```

Rodar relatório de teste:

```bash
docker compose --profile report up --build monitor-client-a
```

Checar o túnel manualmente:

```bash
docker compose exec vpn-client-a ip addr show tun0
docker compose exec vpn-client-a ip route
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
