---
name: Efeitos colaterais da suíte legada
description: Comportamento observado ao validar alterações sem modificar bancos legados.
---

A suíte completa existente pode gravar registros temporários em
`data/diagnostico.db` durante a execução, mesmo quando a alteração em validação
não toca esse banco.

**Why:** a verificação em paralelo com a suíte confundiu uma mutação produzida
pelos próprios testes com o estado inicial do projeto.

**How to apply:** capture hashes dos bancos legados antes da suíte em um comando
separado, execute os testes, compare depois e restaure somente artefatos gerados
pela execução antes de declarar a preservação do legado.