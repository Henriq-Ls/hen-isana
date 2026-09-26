---
name: Fronteira do modo sombra
description: Limite deliberado da comparação entre o núcleo simbólico novo e o fluxo legado.
---

A Fase 3.5 compara somente uma projeção lexical/simbólica comum. O núcleo novo
produz análise estruturada, enquanto o legado ainda produz respostas textuais e
efeitos de sessão; equivalência de resposta pertence à Fase 3.6.

**Why:** declarar equivalência entre tipos de saída diferentes exigiria
reimplementar a resposta estruturada antes da fase autorizada e poderia escolher
automaticamente um resultado novo sem contrato suficiente.

**How to apply:** manter o modo sombra opt-in, registrar ambas as saídas,
preservar fallback para o legado e não promover comparação textual até existir o
contrato da resposta baseada em estrutura.