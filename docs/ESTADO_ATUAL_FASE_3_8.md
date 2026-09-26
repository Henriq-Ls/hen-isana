# HEN-ISANA — ESTADO ATUAL DA FASE 3.8

Data: 2026-09-26
Status: consolidação documental encerrada; próxima fase autorizada somente para inspeção técnica do código
Escopo: estado documental das 16 categorias legadas e sua preparação para revisão futura

## 1. Estado da fase

### O que foi analisado

Foram analisados:

- os valores distintos de `conhecimento.tipo` no legado;
- os 37 registros de conhecimento distribuídos em 16 categorias;
- os exemplos, significados, contextos, respostas padrão, referências e
  evidências documentais;
- as 66 linhas de relações legadas, organizadas em 33 pares reversos;
- o contrato atual e as regras implementadas para conhecimento e relações;
- os artefatos de preparação, revisão, resolução e dry-run da Fase 3.7;
- as reavaliações categoriais produzidas na Fase 3.8.

O problema central era determinar se os tipos livres do legado poderiam ser
relacionados aos tipos canônicos `expressao`, `lexema`, `forma_lexical` ou
`sentido` sem inventar uma correspondência semântica. Também era necessário
separar categorias de conhecimento de tipos de relação legada e preservar a
proveniência para uma etapa futura.

### Critério vigente

A referência semântica atual é
`docs/REAVALIACAO_FINAL_CRITERIO_CATEGORIAS_FASE_3_8.txt`.

Uma categoria só pode sair de `INDEFINIDO` quando todos os registros da
categoria puderem ser sustentados pelo mesmo tipo canônico no nível categorial,
sem depender de decisões individuais ainda não tomadas.

Para `expressao`, isso exige conjuntamente:

1. sequência textual composta ou construção convencional;
2. recorrência observável dentro da categoria;
3. estrutura relativamente estável;
4. função comunicativa identificável como unidade de uso;
5. evidência suficiente para distinguir a construção de combinação produtiva ou
   ocasional.

Termo isolado não é automaticamente `lexema`. O campo `significado` não é
automaticamente `sentido`. `forma_lexical` exige evidência de variantes da
mesma unidade. O rótulo livre do legado e a categoria gramatical não substituem
o tipo canônico.

### Resultado final vigente

Das 16 categorias:

- 1 é candidata a `expressao`: `saudação de período do dia`;
- 15 permanecem `INDEFINIDO`;
- 0 são candidatas a `lexema`;
- 0 são candidatas a `forma_lexical`;
- 0 são candidatas a `sentido`.

`expressão de apresentação` não é mais candidata uniforme a `expressao`.
`prazer em conhecer você` e `muito prazer` podem exigir tratamentos canônicos
distintos; atribuir um tipo único dependeria de decisões individuais.

O candidato para `saudação de período do dia` permanece apenas categorial.
`bom dia`, `boa tarde` e `boa noite` são documentados como fórmulas
convencionais de saudação, mas o uso de `boa noite` como despedida continua
sendo uma pendência semântica. Nenhum dos três registros foi classificado.

### O que está encerrado

Está encerrada a fase documental de:

- inventário das categorias e quantidades;
- rastreamento dos 37 exemplos;
- comparação das categorias com o banco legado;
- separação entre categorias de conhecimento e tipos de relação;
- revisão conservadora do critério de candidato `expressao`;
- consolidação da posição semântica vigente;
- proteção e rastreabilidade dos documentos anteriores.

### O que continua pendente

Continuam pendentes:

- revisão humana do único candidato categorial `expressao`;
- decisão sobre o tratamento semântico de `boa noite` como saudação e
  despedida;
- desdobramento das categorias estruturalmente heterogêneas;
- distinção futura entre expressão, lexema, forma lexical e sentido;
- resolução de componentes, ordem e direção das relações legadas;
- tratamento de `resposta_padrao`, `relacionados` e das perdas de informação;
- revisão independente e autorização específica antes de qualquer aplicação.

Os 70 itens dos artefatos de migração continuam fora de aprovação: 37 propostas
de conhecimento estão pendentes e 33 unidades lógicas de relação estão
conflitantes. Esta consolidação não reprocessa esses itens.

## 2. Documentação utilizada

O inventário abaixo cobre **23 documentos anteriores diretamente relacionados**
à Fase 3.7/Fase 3.8, migração, categorias legadas, contrato, revisão ou
semântica. O próprio documento mestre é o **24º item** do mapa consolidado.

### Mapa de documentação histórica

| Documento | Finalidade | Evidência original? | Contém decisão? | Natureza atual | Substituição/relação | Informação que não pode ser perdida |
|---|---|---|---|---|---|---|
| `docs/ESTADO_ATUAL_FASE_3_8.md` | Estado mestre da Fase 3.8 | Não; consolida fontes | Sim, como estado documental vigente | **REFERÊNCIA ATUAL** | Substitui a necessidade de consultar vários resumos para saber o estado vigente | Precedência da reavaliação final, contagens, pendências e proteções |
| `docs/REAVALIACAO_FINAL_CRITERIO_CATEGORIAS_FASE_3_8.txt` | Última reavaliação semântica conservadora | Usa evidências existentes | Sim, como proposta categorial vigente | **REFERÊNCIA ATUAL** | É a referência semântica mais recente | 1 candidato `expressao`, 15 `INDEFINIDO`, justificativa para retirar a apresentação |
| `docs/INVENTARIO_LEGADO_2026-09-26.txt` | Inventário factual dos bancos e hashes | Sim | Não aprova semântica | **REFERÊNCIA ATUAL** | Fonte factual do estado físico observado | 37 conhecimentos, 217 evidências, 66 relações, hashes e modo somente leitura |
| `docs/MATRIZ_DECISAO_FASE_3_7.txt` | Reconciliação dos 70 itens e 33 unidades de relação | Consolida artefatos de Fase 3.7 | Sim, quanto ao estado de preparação | **REFERÊNCIA ATUAL** | Base de escopo da migração futura | 37 pendentes, 33 conflitantes, nenhum item apto |
| `docs/RESOLUCAO_REVISAO_LOTES_MIGRACAO.json` | Matriz individual completa de resolução | Sim, preserva origem e evidências | Contém classificações de preparação | **REFERÊNCIA ATUAL** | Fonte individual usada pela matriz | 70 propostas, motivos, condições, evidências, hashes e zero aptas |
| `docs/REVISAO_LOTES_MIGRACAO.json` | Revisão anterior dos lotes JSON | Sim, artefato de revisão | Contém classificação anterior | **FONTE HISTÓRICA** | A resolução posterior é a referência consolidada | Conteúdo da revisão que fundamentou a resolução; não apagar para não perder rastreabilidade |
| `docs/PLANO_MIGRACAO_AUDITAVEL.txt` | Procedimento futuro de inventário, dry-run, autorização e aplicação | Consolida regras e fontes | Define limites, não autoriza execução | **REFERÊNCIA ATUAL** | Complementa o mestre com o procedimento futuro | Proibição de conversão automática, preservação, idempotência e rollback |
| `docs/CONTRATO_JSON_CONHECIMENTO.txt` | Especificação do contrato JSON real | Não é fonte do legado | Define contrato técnico | **REFERÊNCIA ATUAL** | Deve ser consultado na futura inspeção técnica | Tipos aceitos, evidências, pendências e limites entre contrato e schema físico |
| `docs/_DOC_PROJETO.txt` | Documento mestre histórico do projeto | Consolida histórico do projeto | Contém decisões de fases anteriores | **REFERÊNCIA ATUAL** contextual | O novo mestre é mais específico para o estado da Fase 3.8 | Hierarquia documental e contexto amplo do projeto |
| `03_ULTIMOS_IMPLEMENTADOS.txt` | Registro consolidado das implementações | Não é fonte semântica | Registra estado técnico | **REFERÊNCIA ATUAL** contextual | Complementa o mestre com o que existe no código | Limites técnicos implementados e distinção entre preparação e aplicação |
| `docs/LOTES_JSON_FASE_3_7.txt` | Organização e proteção dos lotes | Usa propostas já geradas | Define preparação técnica | **FONTE HISTÓRICA** | A matriz atual resume o estado dos lotes | Determinismo, hashes, versões e proteção contra sobrescrita |
| `docs/GERADOR_JSON_DEFINITIVO.txt` | Geração e validação de propostas JSON | Não é fonte semântica | Define ferramenta de preparação | **FONTE HISTÓRICA** | A próxima fase deve inspecionar o código real | Separação entre geração, validação e aplicação |
| `aplicacao/_DOC_APLICACAO.txt` | Documentação da pasta de aplicação | Não é fonte semântica | Registra limites operacionais | **REFERÊNCIA ATUAL** contextual | Complementa os limites de código | Fluxos existentes e fronteira entre preparação e operação |
| `docs/DECISAO_SEMANTICA_FASE_3_8.txt` | Matriz semântica anterior dos 70 itens | Usa evidências do legado | Proposta anterior, não aprovação | **ANÁLISE INTERMEDIÁRIA** | A reavaliação final é a posição semântica vigente | Raciocínios, perdas e evidências anteriores; não converter retrospectivamente em decisão final |
| `docs/MAPA_CATEGORIAS_LEGADAS_FASE_3_8.txt` | Primeiro mapa das 16 categorias | Sim, categorias, quantidades e exemplos | Não aprova categorias | **ANÁLISE INTERMEDIÁRIA** | As reavaliações posteriores refinam o candidato | Lista original, contagens e exemplos rastreados |
| `docs/REAVALIACAO_CATEGORIAS_FASE_3_8.txt` | Primeira reavaliação categorial | Reusa fontes documentais | Proposta intermediária | **ANÁLISE INTERMEDIÁRIA** | Substituída semanticamente pela reavaliação final | Critério estrutural e primeira identificação de categorias heterogêneas |
| `docs/REAVALIACAO_CRITERIO_EXPRESSAO_FASE_3_8.txt` | Revisão rigorosa anterior do candidato `expressao` | Reusa fontes documentais | Proposta intermediária | **ANÁLISE INTERMEDIÁRIA** | Substituída pela máxima conservadoridade | Motivos para retirar quatro candidatos e manter dois na rodada anterior |
| `docs/PROPOSTA_CONTRATO_RELACOES_PILOTO.txt` | Proposta para relações do piloto | Usa relações legadas | Proposta aguardando revisão | **PRECISA DE REVISÃO** | Não foi incorporada ao estado semântico atual | Distinção entre `componente_de_expressao` e `relacionado_no_tema`; não tratar como contrato aprovado |
| `MIGRAÇÃO/PROPOSTA DE REPRESENTAÇÃO INTERMEDIÁRIA E ARQUITETURA LINGUÍSTICA SIMBÓLICA.txt` | Plano amplo anterior de migração e arquitetura | Não é fonte primária dos 37 registros | Contém propostas históricas | **PRECISA DE REVISÃO** | O plano auditável e o mestre são mais recentes para este escopo | Decisões arquiteturais históricas e pontos que ainda dependem de aprovação |
| `docs/_DOC_RESUMO.txt` | Resumo anterior do estado do projeto | Não é fonte primária | Resume decisões anteriores | **REDUNDANTE** | Substituído pelo documento mestre do projeto e por este mestre da Fase 3.8 | Histórico de estado, útil apenas para rastreabilidade |
| `01_PROXIMOS_PASSOS.txt` | Roteiro operacional anterior | Não | Orienta etapas anteriores | **REDUNDANTE** | O estado atual e o plano auditável são mais específicos | Sequência histórica de preparação; candidato a arquivamento futuro |
| `02_IMPLEMENTAR_ AGORA.txt` | Lista de implementação da Parte 3 | Não | Orienta implementação anterior | **REDUNDANTE** | `03_ULTIMOS_IMPLEMENTADOS.txt` e os documentos atuais substituem seu estado | Contexto de decisões de implementação; não usar como autoridade sem revisão |
| `docs/TESTE_GERADOR_JSON.txt` | Registro de teste preliminar do gerador | Não | Valida ferramenta histórica | **REDUNDANTE** | `GERADOR_JSON_DEFINITIVO.txt` e os testes atuais substituem sua função operacional | Resultado histórico do primeiro teste; preservar até política de arquivamento |
| `docs/EXEMPLOS_JSON_CONHECIMENTO.txt` | Índice de exemplos documentais do contrato | Não é fonte legada | Não aprova dados | **FONTE HISTÓRICA** | Complementa o contrato, sem definir categorias legadas | Exemplos de tipos, evidências, relações e pendências do contrato |

Os arquivos JSON individuais em `docs/exemplos_json_conhecimento/` e
`docs/exemplos_fase_1_3_json/` foram tratados como fixtures de contrato, não
como documentos de evidência da Fase 3.8. Os arquivos de teste em `testes/` e os
documentos de performance/neural também não são fontes semânticas desta fase.
Eles não foram apagados, movidos ou renomeados.

### Precedência documental

Quando documentos semânticos anteriores divergem da posição atual, a
precedência é:

1. `docs/REAVALIACAO_FINAL_CRITERIO_CATEGORIAS_FASE_3_8.txt` para o estado
   semântico das 16 categorias;
2. `docs/INVENTARIO_LEGADO_2026-09-26.txt` para quantidades, hashes e estado
   físico do legado;
3. `docs/MATRIZ_DECISAO_FASE_3_7.txt` e
   `docs/RESOLUCAO_REVISAO_LOTES_MIGRACAO.json` para o estado dos 70 itens e
   da preparação de migração;
4. `docs/PLANO_MIGRACAO_AUDITAVEL.txt` e
   `docs/CONTRATO_JSON_CONHECIMENTO.txt` para limites técnicos futuros;
5. documentos anteriores como histórico, sem reescrever suas conclusões.

O conflito conhecido é a redução de dois candidatos anteriores para um. A
reavaliação mais recente não apaga os candidatos antigos: registra por que
`expressão de apresentação` e as outras três categorias foram retiradas da
proposta uniforme.

## 3. Resultado das 16 categorias

| Categoria | Quantidade | Estado atual | Candidato | Evidência principal | Contraevidência | Pendência |
|---|---:|---|---|---|---|---|
| `saudação coletiva` | 7 | `INDEFINIDO` | — | Sete saudações dirigidas a grupos. | Podem ser combinações produtivas de saudação e destinatário. | Desdobrar fórmulas temporais e endereçamento coletivo. |
| `saudação coletiva informal` | 5 | `INDEFINIDO` | — | Cinco padrões de saudação informal com `pessoal` ou `gente`. | Substituição de componentes sugere padrão produtivo. | Separar saudação, vocativo e possível contexto telefônico. |
| `saudação interrogativa` | 3 | `INDEFINIDO` | — | Três formas com função de saudação e pergunta. | Estruturas diferentes, sem unidade comum demonstrada. | Separar pergunta, saudação, sentido e eventual proposição. |
| `saudação de período do dia` | 3 | CANDIDATO | `expressao` | `bom dia`, `boa tarde`, `boa noite`: fórmulas convencionais com padrão temporal. | `boa noite` também é despedida; ordem e componentes não resolvidos. | Revisão humana do candidato categorial e do uso de despedida. |
| `substantivo em expressão de saudação` | 3 | `INDEFINIDO` | — | `dia`, `tarde`, `noite` como termos ligados a saudações. | Categoria gramatical não distingue lexema, forma e sentido. | Definir unidade canônica e papel dos termos. |
| `expressão de reencontro` | 3 | `INDEFINIDO` | — | Função de reencontro em três exemplos. | `quanto tempo` tem estrutura e possível leitura temporal diferente. | Desdobrar antes de qualquer tipo uniforme. |
| `expressão de acolhimento` | 2 | `INDEFINIDO` | — | Função de acolhimento em `seja bem-vindo` e `bem-vindo`. | Estruturas diferentes e possíveis objetos canônicos distintos. | Separar estrutura, gênero, número e papel de `bem`. |
| `expressão de apresentação` | 2 | `INDEFINIDO` | — | Fórmulas de apresentação: `prazer em conhecer você` e `muito prazer`. | Classificação uniforme dependeria de decisões individuais. | Desdobrar as duas formas e resolver o papel de `prazer`. |
| `saudação informal` | 2 | `INDEFINIDO` | — | `oi` e `e aí` são cumprimentos informais. | Mistura termo isolado e sequência composta. | Desdobrar antes de classificar. |
| `adjetivo em expressões de saudação` | 1 | `INDEFINIDO` | — | `bom` aparece em expressões de saudação. | Categoria gramatical não prova lexema; relação com `boa` pendente. | Separar lexema, forma, sentido e componente. |
| `advérbio em expressão de saudação` | 1 | `INDEFINIDO` | — | `bem` aparece em `tudo bem` e `bem-vindo`. | Usos diferentes sem sentido único demonstrado. | Resolver os usos e seus tipos. |
| `expressão de saudação` | 1 | `INDEFINIDO` | — | `olá` tem função de cumprimento e início de conversa. | Termo isolado; o rótulo legado não prova `expressao`. | Distinguir expressão, lexema, forma e sentido. |
| `expressão geral de cumprimento` | 1 | `INDEFINIDO` | — | `saudações` é descrito como cumprimento geral. | A própria descrição admite “palavra ou expressão”. | Definir unidade e alcance semântico. |
| `saudação telefônica` | 1 | `INDEFINIDO` | — | `alô` tem contexto de iniciar ou atender telefone. | Contexto não distingue lexema, forma, sentido ou expressão. | Resolver se o uso telefônico é sentido específico. |
| `substantivo em expressão de apresentação` | 1 | `INDEFINIDO` | — | `prazer` é relacionado a expressões de apresentação. | Termo isolado e categoria gramatical não resolvem o tipo. | Resolver o papel de `prazer` nas formas compostas. |
| `substantivo em saudação coletiva` | 1 | `INDEFINIDO` | — | `pessoal` é usado para dirigir-se a grupo. | Pode ser componente, alvo discursivo ou parte de sentido. | Definir se a função coletiva pertence ao termo ou à expressão. |

**Total:** 16 categorias e 37 registros.

## 4. Critérios semânticos estabelecidos

### Candidato `expressao`

Uma categoria só recebe esse candidato quando a evidência conjunta sustenta
uma unidade de uso para todos os registros da categoria. São necessários
estrutura relativamente estável, convencionalização, recorrência observável,
função comunicativa reconhecível e distinção de combinação ocasional.

O critério é categorial, não uma autorização para criar objetos. Mesmo no único
caso candidato, a revisão não classificou `bom dia`, `boa tarde` ou `boa noite`
individualmente.

### Termo isolado e `lexema`

Uma palavra isolada não prova que a linha represente um lexema abstrato. A
documentação pode estar descrevendo uma forma textual, um uso contextual, um
sentido ou um componente. A categoria gramatical livre também não substitui
essa distinção.

### `significado` e `sentido`

O preenchimento do campo `significado` preserva evidência documental, mas não
prova que o objeto canônico seja um `sentido`. É necessário identificar a
unidade-base, separar leituras e resolver contexto, referências e perdas.

### `forma_lexical`

`forma_lexical` exige evidência de variantes da mesma unidade lexical. Gênero,
número, variante textual, expressão diferente ou palavra relacionada não são
convertidos automaticamente em formas lexicais.

### Heterogeneidade

Quando uma categoria mistura estruturas, funções ou possíveis objetos
canônicos, ela permanece `INDEFINIDO`. Não se deve escolher um único tipo para
evitar o desdobramento necessário.

### Categoria versus registro individual

Uma proposta categorial resume uma hipótese sobre um conjunto documental. Ela
não aprova todos os registros, não resolve exceções e não substitui revisão
individual. A passagem futura de categoria para registro exigirá regra
versionada, evidência preservada, revisão e autorização próprias.

## 5. Categorias que precisam de desdobramento

As seguintes categorias devem ser desdobradas ou analisadas estruturalmente
antes de qualquer classificação canônica:

1. `saudação coletiva`;
2. `saudação coletiva informal`;
3. `saudação interrogativa`;
4. `expressão de reencontro`;
5. `expressão de acolhimento`;
6. `expressão de apresentação`;
7. `saudação informal`.

Isso é uma pendência futura. Nenhum desdobramento deve ser executado agora e
nenhum registro foi separado ou reclassificado nesta consolidação.

## 6. Proteção do legado

Durante a fase documental:

- os registros legados não foram alterados;
- os bancos não foram alterados;
- o mapa original não foi alterado;
- as reavaliações anteriores não foram alteradas;
- nenhum objeto canônico foi criado;
- nenhuma migração foi aplicada;
- nenhuma decisão individual foi tomada;
- nenhum registro foi registrado, autorizado ou aplicado.

As relações `componente_de_expressao` e `relacionado_no_tema` continuam
tratadas como relações legadas, não como categorias semânticas. As 66 linhas
não foram transformadas em objetos nem em pares semânticos novos.

## 7. Estado para entrada na fase de código

A próxima fase pode fazer **inspeção técnica do código**, com foco em:

- confirmar contratos, enums, validações e caminhos de leitura;
- localizar pontos de entrada e proteções contra escrita;
- verificar como uma futura regra versionada poderia preservar proveniência;
- preparar testes de leitura e dry-run isolado, sem aplicar dados.

A próxima fase ainda não pode automaticamente:

- classificar registros;
- converter `INDEFINIDO`;
- criar objetos canônicos;
- alterar banco;
- executar migração;
- chamar `registrar()`;
- chamar `autorizar()`;
- chamar `aplicar()`;
- processar os 70 itens como operação.

Qualquer mudança de classificação exige documento de regra aprovado,
revisão humana, manifesto de cobertura e autorização específica. A entrada na
fase de código não altera o estado semântico vigente.

## 8. Pendências reais

1. Revisar humanamente o candidato categorial
   `saudação de período do dia`.
2. Decidir se `boa noite` deve ter tratamento separado como despedida.
3. Desdobrar as sete categorias listadas na seção 5, sem alterar os registros.
4. Definir a correspondência versionada entre tipos legados e tipos canônicos.
5. Resolver, caso a fase futura avance, expressão, lexema, forma lexical e
   sentido por registro, com evidências e proveniência.
6. Resolver direção, ordem, endpoints e tipo semântico das relações legadas.
7. Definir o tratamento de `resposta_padrao`, `relacionados`, perdas e estados
   de evidência.
8. Executar revisão independente, dry-run isolado e autorização antes de
   qualquer escrita futura.

Não há pendência documental de nova rodada semântica nesta etapa. A fase
documental está encerrada neste estado.

## 9. Validação final

Validações realizadas após a consolidação:

- 16 categorias presentes;
- total de 37 registros consistente;
- exatamente 1 candidato `expressao`;
- exatamente 15 `INDEFINIDO`;
- 0 `lexema`;
- 0 `forma_lexical`;
- 0 `sentido`;
- nenhum registro individual classificado;
- nenhum banco alterado;
- nenhum código alterado;
- nenhum objeto canônico criado;
- nenhum documento anterior apagado, movido ou renomeado.

Este documento é o índice e estado consolidado da Fase 3.8. A documentação está
pronta para a próxima fase: **INSPEÇÃO DO CÓDIGO**.