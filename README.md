# hen-isana

IA simbólica autônoma em Python puro, sem dependências externas. Ela aprende
por perguntas e guarda conceitos, fatos, relações e propostas em SQLite.
Aprender conteúdo não gera arquivos de código. `aprendizado/gerado/` é reservado
a ferramentas ou comportamentos executáveis explicitamente solicitados e
submetidos ao protocolo de segurança.

A interpretação e a conversa locais são determinísticas. As opções explícitas
de aprendizagem por professor ou internet podem consultar fontes externas; as
respostas dessas fontes não são offline nem determinísticas.

## Estrutura

- `main.py`: interface terminal e fluxo de aprendizagem.
- `core/`: interpretação, seleção de perguntas, composição de respostas,
  roteador, validador, versionamento e controlador protegido.
- `protocolo/`: regras e verificador de ações.
- `bancos/`: acesso fixo aos bancos de conhecimento, relações, índice e histórico.
- `aprendizado/`: bancos SQLite de memória, relações e índices; código gerado
  não é usado para persistir conhecimento.
- `data/`: regras fixas da linguagem e diagnóstico operacional.
- `ferramentas/`: ações de busca, criação e edição autorizadas pelo protocolo.
- `backup/`: snapshots, restauração e diagnóstico.
- `testes/`: testes unitários, de isolamento e de fluxo completo.

## Executar

Na raiz do projeto:

```bash
python hen-isana/main.py
```

Digite uma frase. Para encerrar, use `sair`.

Para executar os testes:

```bash
python -m unittest discover -s hen-isana/testes -p "test_*.py" -v
```

## Segurança estrutural

- `ferramentas/` e `aprendizado/gerado/` não importam nem referenciam `core/`.
- O controlador em `core/controlador.py` é o único fluxo autorizado para gravar
  código executável em `aprendizado/gerado/`.
- Toda ação de ferramenta passa por `protocolo/verificador.py`.
- Toda escrita em `aprendizado/gerado/` cria snapshot, valida código em processo
  separado, grava, valida novamente e restaura em caso de falha.
- O código gerado não pode importar `core`, usar carregamento dinâmico ou
  apontar para caminhos do núcleo protegido.
- O validador usa subprocesso e timeout; isso isola o processo principal, mas
  não é um sandbox completo de recursos do sistema.