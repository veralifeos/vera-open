"""ContactsDomain — CRM pessoal / network.

Esquema real (Notion "Contatos & Network"):
  - Nome (title), Status (Não Contatado / Contatado / Respondeu /
    Reunião Marcada / Follow-up), Tipo (Headhunter / Ex-líder /
    Peer / Founder / Recruiter / Cliente / Outro), Última
    Interação (date), Cargo (rich_text), Empresa Atual (rich_text)
"""

from datetime import datetime, timezone

from vera.domains.base import Domain


def _text(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))


def _select(prop: dict) -> str:
    if prop.get("type") == "select":
        return (prop.get("select") or {}).get("name", "")
    return ""


def _date(prop: dict) -> str | None:
    if prop.get("type") == "date":
        return (prop.get("date") or {}).get("start")
    return None


class ContactsDomain(Domain):
    """Domínio de contatos / CRM pessoal."""

    async def collect(self) -> dict:
        """Coleta contatos."""
        collection_id = self.config.get("collection", "")
        if not collection_id:
            return {"contatos": []}

        records = await self.backend.query(
            collection_id=collection_id,
            max_pages=2,
        )

        return {"contatos": [self._parse_contato(r) for r in records]}

    def _parse_contato(self, record: dict) -> dict:
        fields = self.config.get("fields", {})
        props = record.get("properties", {})

        name_field = fields.get("name", "Nome")
        nome = "".join(
            t.get("plain_text", "") for t in props.get(name_field, {}).get("title", [])
        )

        status = _select(props.get(fields.get("status", "Status"), {}))
        tipo = _select(props.get(fields.get("type", "Tipo"), {}))
        ultima_interacao = _date(
            props.get(fields.get("last_interaction", "Última Interação"), {})
        )
        cargo = _text(props.get(fields.get("cargo", "Cargo"), {}))
        empresa = _text(props.get(fields.get("empresa", "Empresa Atual"), {}))

        return {
            "id": record.get("id", ""),
            "nome": nome,
            "status": status,
            "tipo": tipo,
            "ultima_interacao": ultima_interacao,
            "cargo": cargo,
            "empresa": empresa,
        }

    def analyze(self, data: dict) -> dict:
        """Breakdown por status + follow-ups vencidos."""
        contatos = data.get("contatos", [])
        hoje = datetime.now(timezone.utc).date()

        por_status: dict[str, int] = {}
        por_tipo: dict[str, int] = {}
        for c in contatos:
            s = c.get("status") or "—"
            por_status[s] = por_status.get(s, 0) + 1
            t = c.get("tipo") or "—"
            por_tipo[t] = por_tipo.get(t, 0) + 1

        # Follow-ups pendentes ha 7+ dias sem retorno
        stale: list[dict] = []
        for c in contatos:
            if c.get("status") not in ("Contatado", "Follow-up"):
                continue
            ult = c.get("ultima_interacao")
            if not ult:
                continue
            try:
                ult_date = datetime.fromisoformat(ult[:10]).date()
                if (hoje - ult_date).days >= 7:
                    stale.append({**c, "dias_sem_contato": (hoje - ult_date).days})
            except ValueError:
                continue

        # Reuniao marcada (lembrete)
        reunioes = [c for c in contatos if c.get("status") == "Reunião Marcada"]

        return {
            "total": len(contatos),
            "por_status": por_status,
            "por_tipo": por_tipo,
            "stale": stale,
            "reunioes": reunioes,
        }

    def _format_contato(self, c: dict) -> str:
        parts = [c.get("nome") or "?"]
        if c.get("tipo"):
            parts.append(f"[{c['tipo']}]")
        who = []
        if c.get("cargo"):
            who.append(c["cargo"])
        if c.get("empresa"):
            who.append(c["empresa"])
        if who:
            parts.append(f"({' @ '.join(who)})")
        return " ".join(parts)

    def context(self, data: dict, analysis: dict) -> str:
        if analysis["total"] == 0:
            return ""

        lines = [f"CONTATOS: {analysis['total']} ativos"]

        # Breakdown por status
        st = analysis.get("por_status", {})
        if st:
            parts = [f"{k}={v}" for k, v in sorted(st.items(), key=lambda x: -x[1])]
            lines.append("Status: " + " | ".join(parts))

        # Reunioes marcadas (urgente)
        reunioes = analysis.get("reunioes", [])
        if reunioes:
            lines.append(f"REUNIÕES MARCADAS ({len(reunioes)}):")
            for c in reunioes[:5]:
                lines.append(f"  - {self._format_contato(c)}")

        # Follow-ups vencidos
        stale = analysis.get("stale", [])
        if stale:
            lines.append(f"FOLLOW-UPS VENCIDOS ({len(stale)}):")
            for c in stale[:5]:
                lines.append(
                    f"  - {self._format_contato(c)} "
                    f"({c['dias_sem_contato']} dias sem contato)"
                )

        return "\n".join(lines)
