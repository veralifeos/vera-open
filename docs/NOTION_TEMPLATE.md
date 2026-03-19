# Vera — Notion Template

## Template público

**Link do template:** [Vera Life OS — Notion Template](https://veralifeos.notion.site/Vera-Life-OS-Template)

Para usar a Vera com Notion, você tem duas opções:
1. **Automático** — rode `python -m vera setup` e escolha "Criar databases automaticamente"
2. **Manual** — duplique o template acima para seu workspace e conecte a integração

## Como conectar

1. Vá em [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Crie uma nova integração (nome sugerido: "Vera")
3. Copie o token (começa com `ntnl_`)
4. Em cada database do template, clique em `...` → `Connections` → adicione "Vera"
5. Rode `python -m vera setup` e cole o token quando pedido

## Schema das databases

### Vera — Tasks (obrigatório)

| Campo | Tipo | Opções | Obrigatório |
|-------|------|--------|-------------|
| Name | title | — | Sim |
| Status | status | To Do, Doing, Em andamento, Done, Concluído | Sim |
| Prioridade | select | Alta, Média, Baixa (ou customizar) | Sim |
| Deadline | date | — | Sim |
| Tipo | select | Trabalho, Pessoal, Projeto, etc. | Não |

### Vera — Pipeline (opcional)

| Campo | Tipo | Opções | Obrigatório |
|-------|------|--------|-------------|
| Empresa | title | — | Sim |
| Estágio | select | Mapeada, Aplicada, Entrevista, Proposta, Fechou, Descartada | Sim |
| Prioridade | select | Alta, Média, Baixa | Não |
| Próximo Passo | rich_text | — | Não |
| Data Último Contato | date | — | Não |

### Vera — Contacts (opcional)

| Campo | Tipo | Opções | Obrigatório |
|-------|------|--------|-------------|
| Nome | title | — | Sim |
| Status | select | Ativo, Pendente, Inativo | Sim |
| Tipo | select | Profissional, Pessoal, Mentor, etc. | Não |
| Última Interação | date | — | Não |

### Vera — Health (opcional)

| Campo | Tipo | Opções | Obrigatório |
|-------|------|--------|-------------|
| Data | date | — | Sim |
| Exercício | checkbox | — | Não |
| Sono | number | 1-5 | Não |
| Humor | number | 1-5 | Não |
| Notas | rich_text | — | Não |

### Vera — Finances (opcional)

| Campo | Tipo | Opções | Obrigatório |
|-------|------|--------|-------------|
| Data | date | — | Sim |
| Valor | number | — | Sim |
| Categoria | select | Alimentação, Transporte, Moradia, etc. | Não |
| Tipo | select | Entrada, Saída | Sim |
| Notas | rich_text | — | Não |

### Vera — Learning (opcional)

| Campo | Tipo | Opções | Obrigatório |
|-------|------|--------|-------------|
| Título | title | — | Sim |
| Tipo | select | Curso, Livro, Artigo, Podcast, etc. | Não |
| Status | select | Para Fazer, Em Progresso, Concluído | Sim |
| Progresso | number | 0-100 (%) | Não |
| Notas | rich_text | — | Não |

## Personalização

Os nomes dos campos são totalmente configuráveis via `config.yaml`.
Se seus campos têm nomes diferentes (ex: "Title" em vez de "Name"),
ajuste no bloco `domains.tasks.fields` do config.

## Screenshots

<!-- TODO: Adicionar screenshots do template -->
