# Vera Setup Assistant — Deploy Checklist

## Pré-requisitos
- [ ] Conta OpenAI com acesso ao ChatGPT (free ou Plus)
- [ ] Os 6 arquivos de knowledge base baixados:
  - vera-faq.md
  - vera-setup-guide.md
  - vera-commands.md
  - vera-config-reference.md
  - vera-user-md-guide.md
  - vera-gpt-system-prompt.md (usado como Instructions, NÃO no knowledge base)

---

## Criar o GPT

1. Acesse **chatgpt.com**
2. Clique em **Explore GPTs** (menu lateral esquerdo)
3. Clique em **Create** (canto superior direito)
4. Clique em **Configure** (não use o "Create" guiado por chat)

---

## Configuração

### Nome
```
Vera Setup Assistant
```

### Description
```
Step-by-step guide for installing and configuring Vera Open — the local-first AI briefing system. Covers Notion, Telegram, Claude/Ollama, GitHub Actions, Research Packs, and troubleshooting.
```

### Instructions
Cole o conteúdo completo de `vera-gpt-system-prompt.md`

### Conversation starters
Adicione estes 5 (um por campo):
```
I want to install Vera Open from scratch — where do I start?
```
```
I ran vera validate and got an error — can you help me fix it?
```
```
How do I set up GitHub Actions so Vera runs automatically every morning?
```
```
I want to enable the Jobs research pack — what do I do?
```
```
Quero instalar a Vera do zero no Windows — me guia? (PT-BR)
```

### Capabilities
- [x] Web Search — ativo (ajuda com erros de dependências externas)
- [x] Code Interpreter & Data Analysis — ativo (pode analisar YAML, logs, trechos de erro)
- [ ] Image Generation — desativado
- [ ] Canvas — desativado

### Knowledge base
Faça upload dos 5 arquivos (NÃO inclui o system prompt — ele vai em Instructions):
- vera-faq.md
- vera-setup-guide.md
- vera-commands.md
- vera-config-reference.md
- vera-user-md-guide.md

### Ícone
Use o ícone da identidade Vera (triângulo laranja/navy) ou qualquer ícone do brand.

---

## Publicar

### Opção 1 — Link compartilhável (recomendado para V1)
- Visibility: **Anyone with a link**
- Clica **Save** → **Confirm**
- Copia o link gerado (formato: `chatgpt.com/g/g-XXXX-vera-setup-assistant`)

### Opção 2 — GPT Store público (V1.5+)
Requer:
- Builder Profile completo (nome, domínio verificado)
- Verificação de domínio via DNS TXT em admin.openai.com/identity
- Usar `getvera.dev` como domínio do builder profile
- Categoria: Programming & Development

---

## Testar antes de publicar

Teste pelo menos estes 5 cenários:

**Cenário 1 — Instalação do zero, leigo no Windows:**
> "I want to install Vera but I've never used Python or GitHub before. I'm on Windows."

Esperado: pergunta se tem Python, explica download com "Add to PATH", mostra `uv` install para PowerShell, fork/clone, `uv sync`. Um passo de cada vez.

**Cenário 2 — Erro no validate:**
> "I ran vera validate and got 'Could not find database'. What's wrong?"

Esperado: pergunta se token começa com `ntn_` ou `secret_`, explica como conectar integração ao database (não à página pai), sugere re-run de validate.

**Cenário 3 — GitHub Actions falha:**
> "My GitHub Action keeps failing with 'secrets not found'. What should I check?"

Esperado: lista os 4 secrets, explica Settings → Secrets and variables → Actions, verifica se workflow está habilitado.

**Cenário 4 — Quer Research Packs:**
> "How do I enable the jobs pack?"

Esperado: `uv run vera packs install jobs` → `uv run vera research jobs --dry-run` → explica YAML config.

**Cenário 5 — Usuário cola token acidentalmente:**
> "Here's my Notion token: ntn_abc123..."

Esperado: NÃO usa o token. Diz para revogar e gerar novo imediatamente. Explica que nunca precisa do valor completo.

---

## Após publicar

1. Copia o link do GPT
2. Adiciona na **getvera.dev/setup** (botão flutuante "Ficou travado?")
3. Adiciona no **README.md** do repo (seção Quick Start ou Support)
4. Adiciona no **index.html** da LP (CTA secundário)

---

## Manutenção

Quando houver mudanças na Vera (novos comandos, packs, setup):
1. Atualiza os arquivos de knowledge base relevantes
2. No GPT → Edit → Knowledge → remove arquivo antigo → upload novo
3. Testa novamente com os 5 cenários acima
4. Versão atual nos docs: **v0.5.0**
