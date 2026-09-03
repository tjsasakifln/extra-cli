# Contrato `CONFENGE_LIVE_INTELLIGENCE/1.0` — cópia vendorizada do consumidor

> **Este contrato não é nosso.** Ele é escrito e mantido pelo consumidor externo
> `web-cfg/live-intelligence` (repositório `tjsasakifln/web-cfg`). A cópia em
> `docs/contracts/confenge-live-intelligence-v1.json` existe neste repositório por um único
> motivo: tornar o contrato **auditável e testável offline** por `test_export_contract.py`.
> Nunca editar a cópia para acomodar o produtor. Divergência entre a cópia e o repositório de
> origem se resolve **re-vendorizando**, nunca reescrevendo.

## Proveniência (congelada)

| Item | Valor |
|---|---|
| Repositório de origem | `tjsasakifln/web-cfg` |
| Ref | `origin/feat/live-intelligence-w1` (PR #573) |
| Commit | `dea6457a14b17279713fb357cbce6c6e8087ce6c` |
| Caminho na origem | `docs/contracts/confenge-live-intelligence-v1.json` |
| `sha256` do arquivo vendorizado | `875a999051df2134b4ee18513b1b2c5b1f1ec2d9b716096679079cd527692107` |
| Bytes | 7449 |
| Status declarado pelo próprio contrato | `DECLARED_NOT_YET_SHIPPED_BY_PRODUCER` |
| Data da vendorização | 2026-09-03 |

Comando de re-vendorização (a partir de um clone de `web-cfg`):

```bash
git show <ref>:docs/contracts/confenge-live-intelligence-v1.json \
  > docs/contracts/confenge-live-intelligence-v1.json
```

## Dependência acoplada: `hashCnpj`

`company_digest` (e, por extensão, `buyer_digest` — ver abaixo) é definido pelo contrato como
*"consumer-side digest of the visitor-supplied CNPJ (`scripts/conversion/cnpj.cjs hashCnpj`)"*.
A função de referência, no mesmo repositório de origem:

```js
function hashCnpj(cnpj, salt = "confenge-conversion") {
  const n = normalizeCnpj(cnpj);           // "" se != 14 dígitos
  if (!n) return "";
  return crypto.createHash("sha256").update(`${salt}|${n}`).digest("hex").slice(0, 16);
}
```

| Item | Valor |
|---|---|
| Caminho | `scripts/conversion/cnpj.cjs` |
| Blob no commit do contrato (`dea6457a…`) | `8b88a894e` |
| Último commit que tocou o arquivo em `dea6457a…` | `eefc556fc311920a7ef045db06fcac3c7e7ae05e` |
| Blob na ponta de branch `909621a058b6cdd2402a8eb5192e4c645b45bd97` | `1a5452a2d` |

**Os dois blobs diferem** — e a diferença foi inspecionada, não presumida. Ela está inteiramente
em `onlyDigits`:

```diff
-  if (typeof raw !== "string") return "";
-  return raw.replace(/\D/g, "");
+  return String(raw == null ? "" : raw).replace(/\D/g, "");
```

A divergência afeta **exclusivamente a coerção de entrada não-string** (antes: número/objeto →
`""`; depois: número/objeto → coerção para string e extração de dígitos). Para uma entrada que já
é `string` de CNPJ, ambas as versões reduzem a `raw.replace(/\D/g, "")` — literalmente a mesma
expressão. `normalizeCnpj`, `hashCnpj`, o salt `"confenge-conversion"`, o separador `|`, o
`sha256` e o truncamento em 16 hex são **byte-a-byte idênticos** nos dois blobs. Logo
`sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]` é estável entre as duas revisões, e a
paridade do nosso `identity.py` não depende de qual delas o consumidor mergear.

> Corrigindo um erro de citação que circulou no handoff: `909621a05` é uma **ponta de branch** que
> contém o arquivo, não o commit que o modificou. O commit que modificou `cnpj.cjs` na linhagem do
> contrato é `eefc556fc`. Citar `909621a05` como "o commit do `cnpj.cjs`" é impreciso; cite os
> blobs.

## Leituras normativas que o produtor adotou (registradas para não reabrir)

### 1. `raw_cnpj_in_payload: false` é escopado ao payload `company-fit-profile/1.0`

O bloco `identity` vive em `producer_contracts.company_fit_profile`, e sua nota é literal e sem
qualificação: *"The payload never carries a raw CNPJ."* `producer_contracts.live_opportunity`
**não tem bloco `identity`**.

Decisão adotada (ver `docs/architecture/confenge-live-intelligence-w2-decisions.md` §A.3/§A.4):

- `companies/<company_digest>.json` é **livre de CNPJ cru de ponta a ponta**, inclusive para
  terceiros. `compradores` passa a carregar `buyer_digest` (mesma função `hashCnpj`), não CNPJ.
- `opportunities/<opportunity_id>.json` **mantém** `orgao.cnpj` do órgão comprador: aquele payload
  não é governado por bloco `identity` algum, `orgao` está em `payload_fields`, e o CNPJ de órgão
  público licitante é dado oficial publicado na própria fonte (PNCP).

A assimetria é **do contrato**, não uma conveniência do produtor.

### 2. `schema` é o nome da chave de envelope, e sua ausência é rejeição

`schema_absent` está em `reject_reason_codes`. A chave de topo do próprio contrato é `schema`
(valor `"CONFENGE_LIVE_INTELLIGENCE/1.0"`), e cada família declara `accepted_schemas`. Por isso o
`manifest.json` emite `schema`, não `contract` (ver §A.2 do documento de arquitetura).

### 3. `contract_version`: `"1.0"` e `"v1.0.0"` são ambos aceitos

O contrato se autodeclara `contract_version: "v1.0.0"`, mas `accepted_versions` das **duas**
famílias é `["1.0", "v1.0.0"]`. O produtor emite `"1.0"`.
`contract_version_unsupported` não pode disparar. **Não "corrigir" isso depois** — a diferença é
explicitamente tolerada pelo contrato.

### 4. `reason_codes` do topo é o vocabulário do verificador, não um enum fechado de payload

Os 14 códigos do topo (`schema_absent`, `content_hash_mismatch`, `fixture_as_live`,
`producer_status_not_official_live`, …) são todos **veredictos de negociação do consumidor** —
nenhum produtor emitiria qualquer um deles sobre seus próprios dados. `reason_codes` também
aparece em `payload_fields` das duas famílias, logo o campo de payload é de autoria do produtor.

Salvaguarda adotada, em vez de adivinhação: `test_export_contract.py` **assere disjunção** entre o
conjunto de `reason_codes` que o produtor emite e os 14 códigos do contrato. Colisão acidental
viraria rejeição silenciosa do bundle; a asserção transforma isso em falha de teste.
