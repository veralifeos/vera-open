"""PipelineDomain — pipeline de oportunidades de emprego.

Esquema real (Notion "Pipeline de Vagas"):
  - Empresa (title), Vaga (rich_text), Estagio (select),
    Prioridade (A - Top / B - Boa / C - Backup),
    Fit (number 0-10), Proximo Passo (rich_text),
    Data Ultimo Contato (date), Fonte (Vera / Manual)
"""

from datetime import datetime, timezone

from vera.domains.base import Domain


_STAGE_ORDER = [
    "Mapeada",
    "Contato Inicial",
    "Processo",
    "Entrevista",
    "Proposta",
    "Fechou",
    "Descartei",
    "Ghost",
]


def _extract_text(prop: dict, key: str = "rich_text") -> str:
    arr = prop.get(key, [])
    return "".join(t.get("plain_text", "") for t in arr)


def _extract_select(prop: dict) -> str:
    if prop.get("type") == "select":
        return (prop.get("select") or {}).get("name", "")
    return ""


def _extract_number(prop: dict):
    if prop.get("type") == "number":
        return prop.get("number")
    return None


def _extract_date(prop: dict) -> str | None:
    if prop.get("type") == "date":
        date = prop.get("date") or {}
        return date.get("start")
    return None


class PipelineDomain(Domain):
    """Domínio de pipeline de oportunidades de emprego."""

    async def collect(self) -> dict:
        """Coleta vagas ativas do pipeline (exclui Descartei + Ghost)."""
        collection_id = self.config.get("collection", "")
        if not collection_id:
            return {"oportunidades": []}

        filters = {
            "and": [
                {"property": "Estágio", "select": {"does_not_equal": "Descartei"}},
                {"property": "Estágio", "select": {"does_not_equal": "Ghost"}},
            ]
        }

        records = await self.backend.query(
            collection_id=collection_id,
            filters=filters,
            max_pages=2,
        )

        return {"oportunidades": [self._parse_oportunidade(r) for r in records]}

    def _parse_oportunidade(self, record: dict) -> dict:
        fields = self.config.get("fields", {})
        props = record.get("properties", {})

        # Empresa (title)
        title_field = fields.get("title", "Empresa")
        empresa = "".join(
            t.get("plain_text", "") for t in props.get(title_field, {}).get("title", [])
        )

        vaga = _extract_text(props.get(fields.get("vaga", "Vaga"), {}))
        estagio = _extract_select(props.get(fields.get("stage", "Estágio"), {}))
        prioridade = _extract_select(props.get(fields.get("priority", "Prioridade"), {}))
        fit = _extract_number(props.get(fields.get("fit", "Fit"), {}))
        proximo = _extract_text(
            props.get(fields.get("next_action", "Próximo Passo"), {})
        )
        ult_contato = _extract_date(
            props.get(fields.get("last_contact", "Data Último Contato"), {})
        )
        fonte = _extract_select(props.get(fields.get("fonte", "Fonte"), {}))

        return {
            "id": record.get("id", ""),
            "empresa": empresa,
            "vaga": vaga,
            "estagio": estagio,
            "prioridade": prioridade,
            "fit": fit,
            "proximo_passo": proximo,
            "data_ultimo_contato": ult_contato,
            "fonte": fonte,
        }

    def analyze(self, data: dict) -> dict:
        """Breakdown por estagio + alertas."""
        oportunidades = data.get("oportunidades", [])
        hoje = datetime.now(timezone.utc).date()

        por_estagio: dict[str, int] = {}
        for op in oportunidades:
            est = op.get("estagio") or "Sem estágio"
            por_estagio[est] = por_estagio.get(est, 0) + 1

        # Vagas em processo/entrevista/proposta sem contato ha 7+ dias
        stale: list[dict] = []
        for op in oportunidades:
            if op.get("estagio") not in ("Processo", "Entrevista", "Proposta"):
                continue
            ult = op.get("data_ultimo_contato")
            if not ult:
                continue
            try:
                ult_date = datetime.fromisoformat(ult[:10]).date()
                if (hoje - ult_date).days >= 7:
                    stale.append({**op, "dias_sem_contato": (hoje - ult_date).days})
            except ValueError:
                continue

        # Alto fit (>=8) parado em Mapeada
        high_fit_mapeadas = [
            op for op in oportunidades
            if op.get("estagio") == "Mapeada"
            and op.get("fit") is not None
            and op["fit"] >= 8
        ]

        # Tier A (Prioridade "A - Top")
        tier_a = [op for op in oportunidades if "A" in (op.get("prioridade") or "")]

        return {
            "total": len(oportunidades),
            "por_estagio": por_estagio,
            "stale": stale,
            "high_fit_mapeadas": high_fit_mapeadas,
            "tier_a": tier_a,
        }

    def _format_vaga(self, op: dict) -> str:
        parts = [op.get("empresa") or "?"]
        if op.get("vaga"):
            parts.append(f"— {op['vaga']}")
        meta = []
        if op.get("fit") is not None:
            meta.append(f"fit={op['fit']}")
        if op.get("prioridade"):
            meta.append(op["prioridade"])
        if op.get("fonte"):
            meta.append(op["fonte"])
        if meta:
            parts.append(f"[{' | '.join(meta)}]")
        return " ".join(parts)

    def context(self, data: dict, analysis: dict) -> str:
        if analysis["total"] == 0:
            return ""

        lines = [f"PIPELINE: {analysis['total']} vagas ativas"]

        # Breakdown por estagio
        est = analysis.get("por_estagio", {})
        if est:
            parts = []
            for s in _STAGE_ORDER:
                if s in est:
                    parts.append(f"{s}={est[s]}")
            for k, v in est.items():
                if k not in _STAGE_ORDER:
                    parts.append(f"{k}={v}")
            lines.append("Estágio: " + " | ".join(parts))

        stale = analysis.get("stale", [])
        if stale:
            lines.append(f"SEM CONTATO 7+ DIAS ({len(stale)}):")
            for op in stale[:5]:
                lines.append(
                    f"  - {self._format_vaga(op)} "
                    f"(estágio={op['estagio']}, {op['dias_sem_contato']} dias)"
                )

        hf = analysis.get("high_fit_mapeadas", [])
        if hf:
            lines.append(f"ALTO FIT EM MAPEADA ({len(hf)}):")
            for op in hf[:5]:
                lines.append(f"  - {self._format_vaga(op)}")

        tier_a = analysis.get("tier_a", [])
        if tier_a:
            lines.append(f"TIER A ({len(tier_a)}):")
            for op in tier_a[:5]:
                extra = f" → {op['proximo_passo']}" if op.get("proximo_passo") else ""
                lines.append(f"  - {self._format_vaga(op)} [{op.get('estagio')}]{extra}")

        return "\n".join(lines)
