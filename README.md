# isana

<p align="center">
  <strong>Uma inteligência artificial simbólica, construída para aprender, raciocinar e preservar conhecimento.</strong>
</p>

<p align="center">
  <em>Python puro · Memória persistente · Conhecimento estruturado · Aprendizagem controlada · Arquitetura determinística</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.x-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/SQLite-persistência-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Dependências-externas%3A%200-brightgreen" alt="Dependências externas">
  <img src="https://img.shields.io/badge/Arquitetura-simbólica-purple" alt="Arquitetura simbólica">
</p>

---

## Sobre

**isana** é uma inteligência artificial simbólica experimental escrita em Python puro.

O projeto busca construir uma IA cujo conhecimento não dependa exclusivamente de pesos neurais ou de arquivos de código gerados. A memória persistente é representada como **dados estruturados**, armazenados em SQLite, enquanto interpretação, perguntas, relações, proposições, evidências e regras são tratados por componentes explícitos.

A arquitetura foi projetada para separar claramente:

* conversa;
* aprendizagem;
* conhecimento;
* inferência;
* fontes externas;
* ferramentas;
* memória persistente;
* código executável;
* segurança;
* validação.

O princípio central é simples:

> **Aprender conhecimento não significa gerar código.**

Conhecimento é dado.

Comportamento executável é outra coisa e exige um fluxo separado, explícito e validado.

---

## O que é a isana?

A isana não é apenas uma interface de conversa.

Ela está sendo construída como um sistema composto por diferentes camadas capazes de representar e manipular conhecimento de maneira estruturada.

Entre os elementos já presentes na arquitetura estão:

* léxico;
* formas lexicais;
* morfologia;
* sintaxe;
* semântica;
* conceitos;
* proposições;
* fatos;
* relações;
* fontes;
* evidências;
* proveniência;
* confiança;
* incerteza;
* contexto;
* inferência simbólica;
* planos de resposta;
* aprendizagem;
* memória persistente;
* ferramentas autorizadas;
* auditoria;
* rollback.

A arquitetura também diferencia explicitamente aquilo que foi **fornecido**, aquilo que foi **proposto** e aquilo que foi **confirmado**.

Isso é importante porque uma sugestão de uma IA, professor, internet ou outra fonte não deve automaticamente se transformar em verdade persistente.

---

# Princípios

## 1. Conhecimento é dado, não código

A aprendizagem de conteúdo é armazenada na memória estruturada da isana.

Ela não cria automaticamente:

```text
aprendizado/gerado/termo_x.py
aprendizado/gerado/categoria_y.py
aprendizado/gerado/conhecimento_z.py
```

O conhecimento permanece nos bancos SQLite.

`aprendizado/gerado/` é reservado para ferramentas ou comportamentos executáveis solicitados explicitamente e submetidos ao fluxo de segurança.

---

## 2. Fontes não aprovam a própria informação

Professor, Llama, internet e outras fontes externas podem produzir propostas.

Eles não possuem autoridade automática para persistir essas propostas como conhecimento confirmado.

O fluxo conceitual é:

```text
Fonte
  ↓
Proposta
  ↓
Contrato
  ↓
Validação
  ↓
Revisão
  ↓
Autorização
  ↓
API de conhecimento
  ↓
Memória persistente
```

A isana permanece responsável pela coordenação do processo.

---

## 3. A IA não precisa estar presente para o sistema funcionar

A arquitetura foi construída para que o núcleo funcione sem depender de um modelo externo.

Professor, internet e Llama local são fontes/adaptadores opcionais.

Isso mantém uma separação entre:

```text
NÚCLEO
  ├── interpretação
  ├── representação
  ├── regras
  ├── conhecimento
  ├── inferência
  └── memória

FONTES EXTERNAS
  ├── professor
  ├── internet
  └── Llama/Ollama
```

---

## 4. Incerteza não é verdade

Uma hipótese não vira fato simplesmente porque existe.

Uma proposta continua sendo proposta.

Uma inferência continua sendo inferência.

Um conflito continua sendo conflito.

A arquitetura procura preservar:

* fonte;
* evidência;
* proveniência;
* confiança;
* estado;
* premissas;
* conclusão;
* incerteza;
* conflitos.

A inferência simbólica, por exemplo, trabalha somente com regras explicitamente registradas e não transforma automaticamente ausência de prova, hipótese ou candidato em fato.

---

# Arquitetura

A arquitetura atual pode ser visualizada aproximadamente assim:

```text
                         ┌─────────────────────┐
                         │       USUÁRIO       │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      APLICAÇÃO      │
                         │ terminal / sessões  │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
             ┌─────────────┐                 ┌─────────────┐
             │  CONVERSA   │                 │ APRENDIZAGEM│
             └──────┬──────┘                 └──────┬──────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                         ┌─────────────────────┐
                         │  FLUXO DA APLICAÇÃO │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │       CORE          │
                         │ interpretação       │
                         │ perguntas           │
                         │ semântica           │
                         │ inferência           │
                         │ resposta             │
                         │ controle             │
                         └──────────┬──────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                 ┌──────────────┐      ┌──────────────┐
                 │ CONHECIMENTO │      │  PROTOCOLO   │
                 │    / API     │      │  SEGURANÇA   │
                 └──────┬───────┘      └──────┬───────┘
                        │                     │
                        ▼                     ▼
                 ┌──────────────┐      ┌──────────────┐
                 │    SQLite    │      │  FERRAMENTAS │
                 │   memória    │      │  autorizadas │
                 └──────────────┘      └──────────────┘
```

---

# Camadas principais

### `core/`

O núcleo protegido da isana.

Contém componentes relacionados a:

* interpretação;
* perguntas adaptativas;
* composição de respostas;
* inferência;
* roteamento;
* validação;
* versionamento;
* controle;
* representação intermediária;
* resposta estruturada.

O `core/` não deve ser tratado como uma pasta comum de ferramentas.

---

### `aplicacao/`

Coordena os fluxos da aplicação.

É responsável por:

* terminal;
* sessões;
* conversa;
* aprendizagem;
* cadastro;
* integração gradual;
* modo sombra;
* geração de propostas;
* organização de lotes;
* coordenação entre componentes.

---

### `bancos/`

Camada responsável pelo acesso aos bancos SQLite.

O objetivo é impedir que cada componente conheça diretamente o schema físico.

A aplicação trabalha com contratos e APIs; o mapeamento físico permanece centralizado.

---

### `aprendizado/`

Contém a infraestrutura relacionada à memória e aprendizagem.

O SQLite é a memória persistente canônica do conhecimento aprendido.

Aprender um novo conceito não significa criar um novo módulo Python.

---

### `protocolo/`

Define as regras para ações autorizadas.

Ferramentas não devem simplesmente executar uma operação porque receberam uma solicitação.

A ação passa pelo fluxo de verificação definido pelo protocolo.

---

### `ferramentas/`

Contém ações externas autorizadas, como mecanismos de busca, criação ou edição.

Ferramentas ficam separadas do núcleo protegido.

---

### `professor/`

Infraestrutura para fontes de aprendizagem externas.

O projeto preserva:

```text
professor/professor.py
professor/professor_llama.py
```

O professor pode atuar como:

1. **respondente**, respondendo uma pergunta específica;
2. **estruturador**, propondo uma estrutura de conhecimento sem inventar informações ausentes.

---

### `backup/`

Responsável por:

* snapshots;
* restauração;
* diagnóstico;
* proteção antes de operações sensíveis.

---

### `data/`

Regras fixas e informações operacionais utilizadas pelo sistema.

---

### `testes/`

Testes automatizados do projeto.

Incluem testes de:

* contratos;
* API;
* cadastro;
* JSON;
* inferência;
* modo sombra;
* resposta estruturada;
* segurança;
* integridade;
* isolamento;
* idempotência;
* rollback;
* fluxo completo.

---

# Memória e conhecimento

A nova arquitetura de conhecimento foi desenhada para não expor o schema físico aos adaptadores.

Três fontes principais convergem para o mesmo contrato:

```text
entrada manual
       \
        \
JSON ───────► Contrato de Cadastro
        /             │
       /              ▼
IA/professor      Validação
                       │
                       ▼
                API de conhecimento
                       │
                       ▼
                  linguagem.db
```

Isso permite que diferentes fontes produzam propostas sem que nenhuma delas precise conhecer diretamente as tabelas ou colunas do SQLite.

---

# Representação linguística

O núcleo linguístico simbólico trabalha com diferentes níveis de representação.

Entre eles:

```text
texto
  ↓
tokens
  ↓
formas lexicais
  ↓
análise morfológica
  ↓
estrutura sintática
  ↓
representação semântica
  ↓
conceitos / entidades / eventos
  ↓
proposições
  ↓
relações / fatos / evidências
```

A arquitetura também preserva alternativas e ambiguidades quando a informação disponível não permite uma decisão única.

Um termo isolado não é automaticamente tratado como um lexema.

Um significado fornecido pelo usuário não é automaticamente transformado em sentido canônico.

Uma proposição não se torna automaticamente um fato.

Essas distinções fazem parte do modelo.

---

# Inferência simbólica

A isana possui uma camada dedicada à inferência simbólica.

A proposta é trabalhar com:

```text
premissas
   +
regra explícita
   ↓
conclusão
```

Cada conclusão derivada deve preservar sua origem.

Exemplo conceitual:

```text
Premissa A
Premissa B
     │
     ▼
Regra R
     │
     ▼
Conclusão C
```

A conclusão não apaga as premissas que a produziram.

Quando existe conflito, o conflito permanece registrado em vez de ser resolvido silenciosamente.

---

# Resposta estruturada

A geração de resposta também foi separada da interpretação.

Em vez de depender diretamente da frase original, o mecanismo pode receber um `PlanoResposta` contendo elementos como:

* intenção;
* proposições;
* resultados;
* evidências;
* incertezas;
* conflitos;
* inferências;
* proveniência.

A resposta textual é então produzida a partir dessa estrutura.

Isso permite distinguir entre:

```text
"O sistema sabe."
"O sistema inferiu."
"O sistema encontrou uma proposta."
"O sistema não possui evidência suficiente."
```

em vez de transformar tudo em uma única resposta aparentemente certa.

---

# Aprendizagem

A aprendizagem é uma operação explícita.

A interface atual separa:

```text
1 - Conversa
2 - Aprendizagem
```

No modo de aprendizagem, existem fontes diferentes, incluindo:

```text
1 - Conversar e ensinar manualmente
2 - Consultar o professor
3 - Pesquisar na internet e confirmar
4 - Usar o Llama local do Ollama
```

A conversa normal permanece separada da aprendizagem.

Isso evita que simplesmente conversar com a isana faça com que qualquer palavra desconhecida seja automaticamente gravada na memória.

---

# JSON como contrato

JSON não é tratado como código.

Ele é utilizado como formato estruturado de proposta.

O fluxo é:

```text
JSON
 ↓
leitura
 ↓
validação estrutural
 ↓
validação semântica
 ↓
referências
 ↓
duplicidade
 ↓
revisão
 ↓
autorização
 ↓
persistência
```

Campos fora do contrato, tipos inválidos e estruturas incompatíveis devem ser rejeitados.

O JSON não escolhe diretamente uma tabela SQLite.

---

# Modo sombra

A arquitetura possui um modo sombra para integração gradual.

O objetivo é permitir que componentes novos sejam executados de maneira observacional sem substituir imediatamente o comportamento legado.

Conceitualmente:

```text
                 ┌───────────────┐
entrada ────────►│ fluxo legado  │──────► resposta
                 └───────────────┘
                        │
                        │ comparação
                        ▼
                 ┌───────────────┐
                 │ fluxo novo    │
                 └───────────────┘
```

Falhas, ausência de suporte, incompletude e ambiguidades possuem fallback explícito.

O fluxo legado não é substituído simplesmente porque o componente novo existe.

---

# Segurança estrutural

A segurança da isana é baseada principalmente em separação de responsabilidades e fronteiras explícitas.

Entre as regras existentes:

* `core/` é protegido estruturalmente;
* ferramentas passam pelo protocolo de verificação;
* código executável gerado possui fluxo separado;
* snapshots são realizados antes de alterações sensíveis;
* código gerado passa por validação;
* execução é isolada em processo separado;
* falhas podem provocar restauração;
* conteúdo aprendido não cria automaticamente módulos;
* fontes externas não possuem escrita direta no SQLite;
* JSON recebido nunca deve ser executado como código.

A validação por subprocesso e timeout reduz o risco de execução no processo principal, mas não constitui um sandbox completo de recursos do sistema operacional.

---

# Persistência

A memória persistente utiliza SQLite.

A arquitetura separa diferentes responsabilidades entre os bancos, incluindo:

```text
conhecimento
relações
índice de código
histórico de mudanças
linguagem
```

O banco novo de linguagem possui uma representação estruturada separando, entre outros elementos:

* lexemas;
* formas lexicais;
* sentidos;
* conceitos;
* expressões;
* proposições;
* argumentos;
* fatos;
* relações;
* fontes;
* evidências.

A persistência é tratada como memória estruturada, não como geração de código.

---

# Estado atual do projeto

As fundações do projeto já foram implementadas e validadas.

### Concluído

* Parte 1 — fundação, schema, contratos e entradas controladas;
* Parte 2 — núcleo linguístico simbólico;
* Fase 3.1 — API e contrato estruturado do conhecimento;
* Fase 3.2 — cadastro por pacote e entrevista dinâmica;
* Fase 3.3 — ingestão controlada de JSON;
* Fase 3.4 — inferência simbólica;
* Fase 3.5 — modo sombra;
* Fase 3.6 — geração de resposta baseada em estrutura;
* geração e preparação segura de lotes da Fase 3.7;
* consolidação documental da Fase 3.8.

A preparação de lotes foi validada com testes, compilação, verificações de integridade e preservação dos hashes dos bancos.

### Ainda não concluído

A aplicação física dos lotes, migração definitiva do conhecimento legado e desligamento controlado do mecanismo antigo permanecem pendentes e sem autorização.

Isso é intencional.

A arquitetura prioriza primeiro:

```text
representar
   ↓
validar
   ↓
testar
   ↓
auditar
   ↓
revisar
   ↓
autorizar
   ↓
aplicar
```

e não:

```text
descobrir → migrar tudo imediatamente
```

---

# Fase 3.8 — conhecimento legado

A análise atual identificou:

* 37 registros de conhecimento;
* 16 categorias legadas;
* 66 linhas de relações;
* 33 unidades lógicas de relação;
* 70 itens nos artefatos de migração.

A revisão semântica atual é deliberadamente conservadora.

No estado atual, apenas uma categoria é candidata a `expressao` em nível categorial; as outras permanecem `INDEFINIDO` até que exista evidência suficiente para uma classificação segura.
Nenhuma dessas classificações significa que os dados já foram migrados.

Os itens continuam fora de aprovação enquanto aguardam revisão e autorização específica.

---

# Testes e validação

O projeto utiliza a biblioteca `unittest` e valida diferentes níveis da arquitetura.

Exemplo:

```bash
python -m unittest discover -s hen-isana/testes -p "test_*.py" -v
```

Também são utilizados processos de validação como:

```bash
python -m compileall -q core aplicacao bancos testes
```

e verificações de integridade dos bancos SQLite.

Na revalidação da cópia atual, o conjunto direcionado das Fases 3.1–3.6, geradores e ferramenta de teste chegou a **130 testes aprovados**, com `compileall`, `integrity_check` e `foreign_key_check` também aprovados.

A suíte completa ainda possui três falhas legadas conhecidas relacionadas à aprendizagem conversacional. Elas permanecem registradas e não foram mascaradas por alterações nos testes ou no código.

---

# Requisitos

A isana foi projetada para funcionar utilizando a biblioteca padrão do Python.

Dependências principais:

```text
Python 3
SQLite
Git
```

Não é necessária uma lista extensa de frameworks para executar o núcleo.

---

# Executando

Na raiz do projeto:

```bash
python hen-isana/main.py
```

A interface atual funciona pelo terminal.

Depois de iniciar, é possível escolher entre os fluxos disponíveis de conversa e aprendizagem.

Para encerrar:

```text
sair
```

---

# Filosofia do projeto

A isana está sendo construída com uma ideia central:

> **Uma inteligência artificial não precisa tratar tudo como texto e nem transformar tudo em código.**

Conhecimento pode ser representado.

Relações podem ser representadas.

Incertezas podem ser representadas.

Evidências podem ser preservadas.

Inferências podem manter suas premissas.

Conflitos podem permanecer explícitos.

E aprendizagem pode ser tratada como um processo controlado.

A intenção é construir uma arquitetura na qual seja possível saber não apenas **o que** a isana sabe, mas também:

```text
de onde veio
por que foi registrado
qual é seu estado
qual evidência o sustenta
se foi fornecido ou inferido
e se foi realmente confirmado
```

---

# Estrutura resumida

```text
hen-isana/
│
├── main.py
│
├── aplicacao/
│   ├── terminal
│   ├── conversa
│   ├── aprendizagem
│   ├── cadastro
│   ├── modo_sombra
│   └── resposta estruturada
│
├── core/
│   ├── contratos
│   ├── interpretação
│   ├── perguntas
│   ├── inferência
│   ├── resposta
│   ├── controlador
│   ├── validador
│   └── versionamento
│
├── protocolo/
│
├── bancos/
│
├── aprendizado/
│
├── ferramentas/
│
├── professor/
│
├── backup/
│
├── data/
│
├── testes/
│
├── docs/
│
└── aprendizado/bancos/
```

---

# Documentação

A documentação técnica do projeto está concentrada em `docs/`.

Entre os documentos relevantes estão:

```text
docs/_DOC_PROJETO.txt
docs/ESTADO_ATUAL_FASE_3_8.md
docs/CONTRATO_JSON_CONHECIMENTO.txt
docs/PLANO_MIGRACAO_AUDITAVEL.txt
docs/GERADOR_JSON_DEFINITIVO.txt
docs/LOTES_JSON_FASE_3_7.txt
```

O documento mestre registra a arquitetura geral, o estado atual, os módulos, os fluxos e as regras globais do projeto.

---

# Status

```text
┌───────────────────────────────────────────────┐
│                   ISANA                       │
├───────────────────────────────────────────────┤
│ Fundação                    ██████████  OK     │
│ Núcleo linguístico         ██████████  OK     │
│ Contratos                  ██████████  OK     │
│ Cadastro multifonte        ██████████  OK     │
│ Ingestão JSON              ██████████  OK     │
│ Inferência simbólica       ██████████  OK     │
│ Modo sombra                ██████████  OK     │
│ Resposta estruturada       ██████████  OK     │
│ Preparação de migração     ██████████  OK     │
│ Revisão semântica          ██████████  OK     │
│ Migração física            ░░░░░░░░░░  PEND.  │
│ Desligamento do legado     ░░░░░░░░░░  PEND.  │
└───────────────────────────────────────────────┘
```

---

## Licença

Defina aqui a licença escolhida para o projeto.

---

<p align="center">
  <strong>isana</strong>
  <br>
  <sub>Conhecimento estruturado. Memória persistente. Raciocínio simbólico.</sub>
</p>
