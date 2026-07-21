# O golden path pode ser reexecutado sem duplicação

Given populated clean DB
When dual seed and dual snapshot and dual source crawls run
Then stable unique keys remain unique (pncp_id, cnpj_8)
And snapshot ids_sha256 stable across dual runs
