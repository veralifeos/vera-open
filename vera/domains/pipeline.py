"""PipelineDomain — pipeline de oportunidades (opcional).

Esqueleto funcional. Implementação completa na Sessão 2.
"""

from vera.domains.base import Domain


class PipelineDomain(Domain):
    """Domínio de pipeline de oportunidades."""

    async def collect(self) -> dict:
        """Coleta dados do pipeline."""
        fields = self.config.get("fields", {})
        collection_id = self.config.get("collection", "")
        if not collection_id:
            return {"oportunidades": []}

        records = await self.backend.query(
            collection_id=collection_id,
            max_pages=2,
        )

        return {"oportunidades": [self._parse_oportunidade(r) for r in records]}

    def _parse_oportunidade(self, record: dict) -> dict:
        """Converte record para formato interno."""
        fields = self.config.get("fields", {})
        props = record.get("properties", {})

        title_field = fields.get("title", "Empresa")
        title_prop = props.get(title_field, {})
        titulo = "".join(
            t.get("plain_text", "") for t in title_prop.get("title", [])
        )

        stage_field = fields.get("stage", "Estágio")
        stage_prop = props.get(stage_field, {})
        estagio = ""
        if stage_prop.get("type") == "select":
            estagio = (stage_prop.get("select") or {}).get("name", "")

        return {
            "id": record.get("id", ""),
            "titulo": titulo,
            "estagio": estagio,
        }

    def analyze(self, data: dict) -> dict:
        """Analisa pipeline."""
        oportunidades = data.get("oportunidades", [])
        return {"total": len(oportunidades)}

    def context(self, data: dict, analysis: dict) -> str:
        """Gera contexto do pipeline para o briefing."""
        if analysis["total"] == 0:
            return ""
        return f"PIPELINE: {analysis['total']} oportunidades ativas"
