"""ContactsDomain — CRM pessoal (opcional).

Esqueleto funcional. Implementação completa na Sessão 2.
"""

from vera.domains.base import Domain


class ContactsDomain(Domain):
    """Domínio de contatos / CRM pessoal."""

    async def collect(self) -> dict:
        """Coleta contatos ativos."""
        collection_id = self.config.get("collection", "")
        if not collection_id:
            return {"contatos": []}

        records = await self.backend.query(
            collection_id=collection_id,
            max_pages=2,
        )

        return {"contatos": [self._parse_contato(r) for r in records]}

    def _parse_contato(self, record: dict) -> dict:
        """Converte record para formato interno."""
        fields = self.config.get("fields", {})
        props = record.get("properties", {})

        name_field = fields.get("name", "Nome")
        name_prop = props.get(name_field, {})
        nome = "".join(t.get("plain_text", "") for t in name_prop.get("title", []))

        return {
            "id": record.get("id", ""),
            "nome": nome,
        }

    def analyze(self, data: dict) -> dict:
        """Analisa contatos."""
        contatos = data.get("contatos", [])
        return {"total": len(contatos)}

    def context(self, data: dict, analysis: dict) -> str:
        """Gera contexto de contatos para o briefing."""
        if analysis["total"] == 0:
            return ""
        return f"CONTATOS: {analysis['total']} ativos"
