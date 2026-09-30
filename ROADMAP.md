# Roadmap do DBA Monitor

Este documento registra a direcao de evolucao do projeto. A ideia central e
transformar o gerador de relatorios por VPN em uma plataforma leve de
observabilidade DBA multi-cliente.

## Visao

O DBA Monitor deve permitir acompanhar varios clientes ao mesmo tempo, cada um
com sua propria VPN, configuracao de banco, agenda de coleta e historico de
relatorios. A aplicacao deve continuar simples de operar via Docker, mas ganhar
estado, dashboard, alertas e diagnosticos mais inteligentes.

## Proximo nivel

### 1. Modelo de clientes e jobs

- Configurar varios clientes no mesmo projeto.
- Cada cliente deve ter VPN, banco, agenda, token, diretorios e retencao
  proprios.
- Registrar execucoes de jobs com status como `queued`, `running`, `success` e
  `failed`.
- Guardar duracao, erro, arquivos gerados, horario de inicio/fim e proxima
  execucao prevista.
- Evitar que requests HTTP executem trabalho pesado diretamente.

### 2. Dashboard web

- Criar uma tela principal com todos os clientes.
- Mostrar status da VPN, status do banco, ultima coleta e ultimo relatorio.
- Exibir falhas recentes e duracao dos jobs.
- Permitir gerar relatorio sob demanda.
- Expor links para HTML, PDF e CSV.
- Mostrar tendencias simples: conexoes, locks, tamanho dos bancos e queries
  longas.

### 3. Alertas

- Enviar alertas por Telegram, e-mail, Discord ou Slack.
- Alertar quando a VPN cair.
- Alertar quando o banco ficar inacessivel.
- Alertar para locks aguardando por muito tempo.
- Alertar para queries longas.
- Alertar para crescimento anormal de banco ou tabela.
- Alertar para autovacuum/analyze atrasado.
- Alertar para numero alto de conexoes.
- Alertar para disco ou tablespace critico, quando houver permissao.

### 4. Historico e comparacao

- Guardar metricas em SQLite ou PostgreSQL local.
- Comparar hoje, ontem e os ultimos 7 dias.
- Detectar crescimento de bancos e tabelas.
- Detectar SQLs que pioraram em tempo total, tempo medio ou I/O.
- Mostrar problemas novos desde o ultimo relatorio.
- Aplicar retencao automatica para dados e relatorios antigos.

### 5. Relatorio mais inteligente

- Adicionar uma secao de diagnostico no relatorio.
- Gerar observacoes como:
  - banco que cresceu muito em 24h;
  - tabela que concentra muitas tuplas mortas;
  - SQL com tempo medio alto;
  - SQL com alto consumo de I/O;
  - aumento relevante de conexoes;
  - locks ou queries longas recorrentes.
- Comecar com regras deterministicas simples antes de usar IA.
- Adicionar modo de sanitizacao para ocultar literais ou trechos sensiveis de
  SQL.

### 6. Arquitetura de execucao

- Separar API, scheduler e worker.
- Usar uma fila simples para jobs.
- Comecar com SQLite para reduzir dependencia operacional.
- Evoluir para PostgreSQL local se o volume justificar.
- Garantir lock por cliente e tipo de job.
- Registrar logs estruturados por execucao.

### 7. Seguranca e empacotamento

- Manter token por cliente.
- Manter a API local por padrao.
- Documentar explicitamente como expor a API com firewall ou reverse proxy.
- Adicionar secret scanning no CI.
- Garantir que `environment/`, relatorios reais e arquivos de credenciais nunca
  sejam versionados.
- Criar exemplos de configuracao sem dados sensiveis.

## Ordem sugerida

1. Criar registry de clientes e jobs.
2. Persistir estado em SQLite.
3. Transformar `POST /reports/run-now` em criacao de job assíncrono.
4. Criar endpoints para listar jobs, ver detalhes e baixar artefatos.
5. Criar dashboard web simples.
6. Adicionar historico de metricas.
7. Adicionar alertas.
8. Adicionar diagnosticos no relatorio.
9. Melhorar empacotamento multi-cliente.

## Criterio de sucesso

O projeto deixa de ser apenas um executor de relatorio quando for possivel abrir
uma unica tela e responder rapidamente:

- quais clientes estao online;
- qual VPN ou banco esta com problema;
- quando foi a ultima coleta;
- quais relatorios foram gerados;
- quais problemas apareceram ou pioraram;
- quais jobs falharam e por que falharam.
