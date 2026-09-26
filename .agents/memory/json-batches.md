---
name: Lotes JSON da Fase 3.7
description: Decisão durável sobre fontes elegíveis e proteção de lotes de conhecimento.
---

Somente propostas JSON já estruturadas no contrato podem ser reempacotadas em
lotes. A preparação separa fonte, assunto, lote e versão, registra hashes e
contagens em manifesto determinístico e nunca sobrescreve uma versão com bytes
diferentes. Bancos legados, banco destino, configuração, código, snapshots e
fontes externas não são convertidos automaticamente em conhecimento.

**Why:** a geração em escala precisa ser reproduzível e auditável sem
transformar dados técnicos, históricos ou incertos em conhecimento persistente.

**How to apply:** antes de qualquer geração, confirme a fonte no inventário;
use o gerador e o contrato reais; injete `IngestaoJSON.dry_run()` somente para
validação; deixe registro, autorização, aplicação e migração para etapas
explícitas posteriores.