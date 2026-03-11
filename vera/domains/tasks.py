"""TasksDomain — domínio obrigatório de tarefas.

Busca, rankeia e gera contexto de tarefas via StorageBackend.
Nomes de campos configuráveis via config.
"""

from datetime import datetime, timezone

from vera.domains.base import Domain


class TasksDomain(Domain):
    """Domínio de tarefas — obrigatório em toda instalação."""

    async def collect(self) -> dict:
        """Coleta tarefas ativas do backend."""
        fields = self.config.get("fields", {})
        status_field = fields.get("status", "Status")
        status_active = fields.get("status_active", ["To Do", "Doing"])

        # Filtro: status em qualquer dos valores ativos
        # Notion API: campo "Status" pode ser tipo "select" ou "status"
        # Lê o tipo do filtro do config (default: "select" para databases PT-BR)
        filter_type = fields.get("status_filter_type", "select")
        filters = {
            "or": [
                {"property": status_field, filter_type: {"equals": s}} for s in status_active
            ]
        }

        sorts = [{"property": fields.get("deadline", "Deadline"), "direction": "ascending"}]

        collection_id = self.config.get("collection", "")
        if not collection_id:
            return {"tarefas": []}

        records = await self.backend.query(
            collection_id=collection_id,
            filters=filters,
            sorts=sorts,
            max_pages=3,
        )

        return {"tarefas": [self._parse_tarefa(r) for r in records]}

    def _parse_tarefa(self, record: dict) -> dict:
        """Converte record do backend para formato interno."""
        fields = self.config.get("fields", {})
        props = record.get("properties", {})

        # Extrai título
        title_field = fields.get("title", "Name")
        title_prop = props.get(title_field, {})
        titulo = "".join(t.get("plain_text", "") for t in title_prop.get("title", []))

        # Extrai status
        status_field = fields.get("status", "Status")
        status_prop = props.get(status_field, {})
        status = ""
        if status_prop.get("type") == "status":
            status = (status_prop.get("status") or {}).get("name", "")
        elif status_prop.get("type") == "select":
            status = (status_prop.get("select") or {}).get("name", "")

        # Extrai prioridade
        priority_field = fields.get("priority", "Prioridade")
        priority_prop = props.get(priority_field, {})
        prioridade = ""
        if priority_prop.get("type") == "select":
            prioridade = (priority_prop.get("select") or {}).get("name", "")

        # Extrai deadline
        deadline_field = fields.get("deadline", "Deadline")
        deadline_prop = props.get(deadline_field, {})
        deadline = None
        if deadline_prop.get("type") == "date" and deadline_prop.get("date"):
            deadline = deadline_prop["date"].get("start")

        # Extrai categoria/tipo
        category_field = fields.get("category", "Tipo")
        category_prop = props.get(category_field, {})
        categoria = ""
        if category_prop.get("type") == "select":
            categoria = (category_prop.get("select") or {}).get("name", "")

        return {
            "id": record.get("id", ""),
            "titulo": titulo,
            "status": status,
            "prioridade": prioridade,
            "deadline": deadline,
            "categoria": categoria,
        }

    async def collect_completed(self) -> list[dict]:
        """Coleta tarefas concluídas do backend (para weekly review)."""
        fields = self.config.get("fields", {})
        status_field = fields.get("status", "Status")
        status_done = fields.get("status_done", ["Done", "Concluído"])
        filter_type = fields.get("status_filter_type", "select")

        filters = {
            "or": [
                {"property": status_field, filter_type: {"equals": s}} for s in status_done
            ]
        }

        collection_id = self.config.get("collection", "")
        if not collection_id:
            return []

        records = await self.backend.query(
            collection_id=collection_id,
            filters=filters,
            sorts=[{"timestamp": "last_edited_time", "direction": "descending"}],
            max_pages=1,
        )

        return [self._parse_tarefa(r) for r in records]

    def analyze(self, data: dict) -> dict:
        """Analisa tarefas: atrasadas, por prioridade, score."""
        tarefas = data.get("tarefas", [])
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        atrasadas = []
        hoje_list = []
        sem_deadline = []

        for t in tarefas:
            if not t.get("deadline"):
                sem_deadline.append(t)
            elif t["deadline"] < hoje:
                atrasadas.append(t)
            elif t["deadline"] == hoje:
                hoje_list.append(t)

        return {
            "total": len(tarefas),
            "atrasadas": atrasadas,
            "hoje": hoje_list,
            "sem_deadline": sem_deadline,
        }

    def context(self, data: dict, analysis: dict) -> str:
        """Gera texto de contexto para o briefing."""
        lines = []
        lines.append(f"TAREFAS: {analysis['total']} ativas")

        if analysis["atrasadas"]:
            nomes = ", ".join(t["titulo"] for t in analysis["atrasadas"])
            lines.append(f"ATRASADAS ({len(analysis['atrasadas'])}): {nomes}")

        if analysis["hoje"]:
            nomes = ", ".join(t["titulo"] for t in analysis["hoje"])
            lines.append(f"HOJE ({len(analysis['hoje'])}): {nomes}")

        # Top 5 tarefas com deadline (próximas)
        com_deadline = [t for t in data["tarefas"] if t.get("deadline")]
        top = com_deadline[:5]
        if top:
            lines.append("PRÓXIMAS:")
            for t in top:
                prio = f" [{t['prioridade']}]" if t.get("prioridade") else ""
                lines.append(f"  - {t['titulo']}{prio} (deadline: {t['deadline']})")

        return "\n".join(lines)
