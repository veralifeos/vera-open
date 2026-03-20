# Vera Open — USER.md Guide
Version: 0.5.0

`workspace/USER.md` is your personal profile file. Vera reads it at briefing time to understand your context, priorities, and preferences. The more specific you are, the more relevant the briefings.

USER.md is gitignored — it stays on your machine and never goes to the repository.

---

## How it works

Vera injects the full content of USER.md into the AI context every briefing. This means:
- Your priorities directly influence task ranking (+20 score boost per matching keyword, max +40)
- Your "O que NAO quero ouvir" section suppresses irritating patterns
- Your "O que QUERO ouvir" section amplifies what matters
- The feedback loop section contains auto-generated inferences about your behavior

---

## Getting started

```
cp workspace/USER.example.md workspace/USER.md
```

Then edit USER.md with your real information. Remove the example text and HTML comments.

---

## Sections to fill manually

### ## Situacao atual
Describe your current professional situation in 2-4 sentences.

Example:
```
Em recolocação desde janeiro. Trabalhando em freelas de branding enquanto busco CLT em produto/marketing. Stack: GA4, HubSpot, Clarity, Figma.
```

### ## Prioridades do mes
Your top 2-5 priorities right now. Use simple numbered items.

**These directly affect task ranking.** Vera extracts keywords from this section and boosts matching tasks by +20 (max +40).

Example:
```
1. Pipeline de vagas ativo — foco em PMM/CRO/Growth, CLT R$12-18k
2. Fechar proposta SEO para cliente B até dia 20
3. Vera v0.5 operacional com feedback loop
```

### ## Contexto operacional
Active projects, clients, schedule, and relevant context.

Example:
```
- Horário: Acordo 10h, pico de energia à noite. Sexta é dia de silêncio.
- Foco semanal: Segunda e quarta: trabalho profundo. Demais: reuniões e admin.
- Restrições: Não agendar reuniões antes das 14h.
- Ferramentas: Notion, Figma, VS Code, Slack
```

### ## O que NAO quero ouvir
Task types, topics, or phrasing patterns you want Vera to avoid. Be specific.

Example:
```
- Frases motivacionais genéricas
- Cobrança sobre tarefas que já sei que estão atrasadas, sem sugerir ação concreta
- Qualquer coisa sobre "equilíbrio vida-trabalho" ou "jornada"
- Listar tarefas que não têm prazo nem urgência real
```

### ## O que QUERO ouvir
Specific alerts, patterns, or insights you want highlighted.

Example:
```
- Alertas sobre deadlines que estou esquecendo
- Quando uma tarefa está parada há muito tempo: sugerir quebrar, delegar ou arquivar
- Reconhecer quando tive uma boa semana antes de cobrar
- Me lembrar de follow-ups no pipeline quando a janela está fechando
```

### ## Dominios ativos
Which Vera domains are most relevant to you right now.

Example:
```
- Trabalho: vagas, freelas, projetos
- Pessoal: tarefas domésticas, saúde, estudos
- Financeiro: pendências, pagamentos
```

---

## Feedback loop section (managed automatically)

### ## Feedback loop

This section is written by Vera's automated feedback system. **Do not edit it manually** except to:
- Remove inferences you disagree with (each line says "remova esta linha se discordar")
- Add manual calibrations in the `### Calibrações ativas` sub-section

### How it works

1. **Observation** — Every briefing saves one observation (tasks suggested, completed, energy score, pack results)
2. **Signal detection** — After 5+ observations, Vera detects behavioral signals
3. **Inference** — Signals become inferences written to this section
4. **Expiry** — Each inference expires after 30 days

### The 5 signals Vera detects

| Signal | Triggers when... |
|--------|-----------------|
| `carga` | Average energy < 5 in last 7 days with 3+ briefings |
| `prioridade_real` | Task completed after 4+ mentions (reveals what you actually prioritize) |
| `zona_morta` | Task with 7+ mentions, never completed (dead zone) |
| `pack_irrelevante` | Research pack returns 0 results in 5+ consecutive runs |
| `ritmo` | 80%+ of completions happen on the same weekday |

### Rules
- Minimum 5 briefings before any inference fires
- Maximum 15 active inferences at a time
- Each inference has a unique ID — same task produces same ID across weeks (no duplicates)
- The writer only modifies lines starting with `- [inferido` — all other content in this section is preserved

### Example of what Vera writes
```
- [inferido 2026-03-20] Prioridade real detectada: "Pipeline Vera Open" (concluída após 6 menções) — remova esta linha se discordar
- [inferido 2026-03-18] Zona morta: "Organizar emails" (8x sem ação) — remova esta linha se discordar
```

### Manual calibrations

You can add a `### Calibrações ativas` sub-section inside Feedback loop for temporary adjustments:

```
### Calibrações ativas
- Ignorar tarefas do projeto X até o dia 30 — em espera deliberada
- Priorizar candidaturas internacionais esta semana
```

These are preserved by the writer and never overwritten.

### CLI commands

```
uv run vera feedback analyze   # Run analysis manually (same as Sunday auto-run)
uv run vera feedback status    # Show observation count and active inferences
uv run vera feedback clear     # Remove all inferences, reset state
```

The feedback loop runs automatically via GitHub Actions every Sunday at 17:00 BRT.

---

## Tips

- Be specific: "Apply to 5 PMM jobs on Himalayas" beats "job search"
- Update monthly or when your situation changes significantly
- The "O que NAO quero ouvir" section has immediate impact on briefing tone
- The "Prioridades do mes" section directly boosts matching task scores
- Leave "Feedback loop" section alone — Vera fills it in
- Remove inferences you disagree with — Vera respects your edits
