"""CheckSemanalDomain -- leitura e interpretacao do Check Semanal.

Database Notion com schema:
- Semana (title): ex "S11 (10-16 mar)"
- Energia, Vida Pratica, Carreira, Sanidade (number 0-10)
- Highlight (rich_text)
"""

from vera.domains.base import Domain


class CheckSemanalDomain(Domain):
    """Dominio de check-in semanal com notas 0-10."""

    async def collect(self) -> dict:
        """Coleta registros do Check Semanal (ultimos 2)."""
        collection_id = self.config.get("collection", "")
        if not collection_id:
            return {"checks": []}

        records = await self.backend.query(
            collection_id=collection_id,
            filters=None,
            sorts=[{"property": "Semana", "direction": "descending"}],
            max_pages=1,
        )

        checks = [self._parse_check(r) for r in records[:2]]
        return {"checks": checks}

    def _parse_check(self, record: dict) -> dict:
        """Converte record do backend para formato interno."""
        fields = self.config.get("fields", {})
        props = record.get("properties", {})

        # Semana (title)
        semana_field = fields.get("semana", "Semana")
        semana_prop = props.get(semana_field, {})
        semana = "".join(
            t.get("plain_text", "") for t in semana_prop.get("title", [])
        )

        # Dimensoes (number 0-10)
        dimensoes = {}
        for dim in ["Energia", "Vida Pratica", "Carreira", "Sanidade"]:
            field_name = fields.get(dim.lower().replace(" ", "_"), dim)
            dim_prop = props.get(field_name, {})
            valor = dim_prop.get("number")
            if valor is not None:
                dimensoes[dim] = valor

        # Highlight (rich_text)
        highlight_field = fields.get("highlight", "Highlight")
        highlight_prop = props.get(highlight_field, {})
        highlight = "".join(
            t.get("plain_text", "")
            for t in highlight_prop.get("rich_text", [])
        )

        return {
            "semana": semana,
            "dimensoes": dimensoes,
            "highlight": highlight,
        }

    def analyze(self, data: dict) -> dict:
        """Analisa checks: faixas, media, tendencia."""
        checks = data.get("checks", [])
        if not checks:
            return {"disponivel": False}

        atual = checks[0]
        dims = atual.get("dimensoes", {})

        if not dims:
            return {"disponivel": False}

        # Faixas por dimensao
        faixas = {}
        for dim, valor in dims.items():
            if valor <= 3:
                faixas[dim] = {"valor": valor, "faixa": "vermelho", "label": "precisa de atencao"}
            elif valor <= 6:
                faixas[dim] = {"valor": valor, "faixa": "amarelo", "label": "funcional mas nao ideal"}
            else:
                faixas[dim] = {"valor": valor, "faixa": "verde", "label": "semana boa"}

        # Media
        media = sum(dims.values()) / len(dims) if dims else 0

        # Tendencia (comparacao com semana anterior)
        tendencia = {}
        if len(checks) >= 2:
            anterior = checks[1].get("dimensoes", {})
            for dim in dims:
                if dim in anterior:
                    diff = dims[dim] - anterior[dim]
                    if diff > 0:
                        tendencia[dim] = f"+{diff} (subindo)"
                    elif diff < 0:
                        tendencia[dim] = f"{diff} (descendo)"
                    else:
                        tendencia[dim] = "estavel"

        # Cruzamentos
        alertas = []
        energia = dims.get("Energia", 5)
        carreira = dims.get("Carreira", 5)
        if energia <= 3 and carreira >= 7:
            alertas.append(
                "Energia baixa + Carreira alta = voce esta forcando. "
                "Reduz escopo ou descansa."
            )
        if energia <= 3 and dims.get("Sanidade", 5) <= 3:
            alertas.append(
                "Energia e Sanidade ambas baixas. Priorize recuperacao."
            )

        return {
            "disponivel": True,
            "semana": atual.get("semana", ""),
            "faixas": faixas,
            "media": round(media, 1),
            "tendencia": tendencia,
            "alertas": alertas,
            "highlight": atual.get("highlight", ""),
            "carga_reduzida": media < 5,
        }

    def context(self, data: dict, analysis: dict) -> str:
        """Gera texto de contexto para injetar no briefing."""
        if not analysis.get("disponivel"):
            return ""

        lines = [f"=== CHECK SEMANAL ({analysis['semana']}) ==="]

        for dim, info in analysis.get("faixas", {}).items():
            trend = ""
            if dim in analysis.get("tendencia", {}):
                trend = f" | {analysis['tendencia'][dim]}"
            lines.append(
                f"- {dim}: {info['valor']}/10 ({info['label']}{trend})"
            )

        lines.append(f"- Media: {analysis['media']}/10")

        if analysis.get("highlight"):
            lines.append(f"- Highlight: {analysis['highlight']}")

        for alerta in analysis.get("alertas", []):
            lines.append(f"- ALERTA: {alerta}")

        if analysis.get("carga_reduzida"):
            lines.append("- CARGA REDUZIDA: media < 5, sugerir menos prioridades e descanso")

        return "\n".join(lines)
