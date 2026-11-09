# ADR — projeção pública para pesquisa de mercado governamental

Data: 2026-11-09. Decisão: EXECUTE_NOW, autorizada pelo fundador para estruturar,
implementar e publicar no site CONFENGE uma ferramenta estratégica com os
contratos persistidos. A decisão não encerra incidentes ou campanhas existentes.

## Decisão

O Extra mantém aquisição, identidade e proveniência. Um consumidor interno lê
somente colunas autorizadas de `pncp_supplier_contracts`, em transação READ ONLY
REPEATABLE READ, e produz o contrato `confenge.market-radar/v1`. O web-cfg serve
a experiência pública em `/ferramentas/radar-mercado-publico/`. Não há consulta
PNCP durante pesquisas públicas, novo Data Lake, CRM ou ação comercial.

A projeção SQLite FTS5 é descartável, privada e imutável por SHA-256. O pointer
é substituído atomicamente após validação. Os metadados também estão dentro do
arquivo, vinculando cobertura e datas ao hash. O processo produtor tem usuário
de sistema e papel PostgreSQL dedicados; o runtime web tem somente leitura.
O exportador roda de release isolada, sem editar o checkout operacional.

## Semântica

Janela fixa de 24 meses pela publicação original, somente pessoas jurídicas
ativas com qualidade VALID e identidade oficial PNCP válida. Deduplicação por
contrato oficial, preservando o registro mais recente. Identificadores de
drill-down são opacos; textos são sanitizados. Links oficiais conservam os
identificadores públicos necessários ao PNCP.

O campo legado de valor mistura bases global, inicial e estimada. A projeção
conserva valor informado por registro e proíbe agregação financeira e ranking
por valor. Fim de vigência não é previsão de nova licitação. Contagens medem
o acervo observado, não todo o mercado. O contrato documenta exclusões.

`source_as_of` é o corte transacional; `generated_at`, a preparação;
`ingestion_latest_at`, a última incorporação observada no universo elegível.
Nenhuma delas afirma atualização individual ou cobertura censitária.

## Operação e efeitos

Cadência própria de quatro horas, sem OnSuccess/Requires/BindsTo do crawler.
Não participa da autoridade comercial, membership, feed, dispatch ou SMTP.
Expiração ou falha fecha apenas o radar. Retenção limitada e verificação de
espaço evitam crescimento indefinido. O website valida hash, contrato,
integridade e idade antes do uso. Não publica o arquivo nem credenciais.

Aceite exige testes adversariais, CI do SHA integrado, exportação real,
reconciliação e verificação pública. O estado operacional se limita à
capacidade demonstrada. Contrato: `../contracts/market-radar-v1.md`.
