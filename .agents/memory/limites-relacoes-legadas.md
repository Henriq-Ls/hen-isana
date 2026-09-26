---
name: Limites das relações legadas
description: Fronteiras semânticas observadas no piloto de relações da migração legada.
---

O contrato autorizado representa somente dois casos legados: a relação embutida
`componente_de_expressao` de `expressao` para `lexema`, com ordem apenas quando a
ocorrência lexical é única, e `relacionado_no_tema` entre duas `expressao` com
direção explicitamente `simetrica`. Outros endpoints e direções continuam fora
do escopo.

**Why:** a retomada controlada autorizou esses dois ajustes mínimos para repetir
o piloto sem migrar registros, aplicar propostas ou alterar o legado.

**How to apply:** preserve proveniência e evidências; deixe ordem zero, múltipla
ou ambígua pendente; deduplicate as duas orientações simétricas somente na
persistência autorizada; repita o piloto apenas em ambiente temporário com
`dry_run()`.