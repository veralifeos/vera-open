"""TasksDomain — domínio obrigatório de tarefas.

Busca, rankeia e gera contexto de tarefas via StorageBackend.
Nomes de campos configuráveis via config.
"""

from datetime import datetime, timezone

from vera.domains.base import Domain


def _select_value(prop: dict) -> str:
    """Extrai nome de um prop select, ou string vazia."""
    if prop.get("type") == "select":
        return (prop.get("select") or {}).get("name", "")
    return ""


def _rich_text_value(prop: dict) -> str:
    """Extrai texto concatenado de um prop rich_text."""
    if prop.get("type") == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
    return ""


def _read_any_text(prop: dict) -> str:
    """Tenta extrair texto de qualquer tipo de prop (formula, select, number,
    rich_text, relation count). Usado quando o schema pode variar."""
    t = prop.get("type", "")
    if t == "formula":
        f = prop.get("formula") or {}
        ft = f.get("type", "")
        if ft == "string":
            return f.get("string") or ""
        if ft == "number" and f.get("number") is not None:
            return str(f["number"])
        if ft == "boolean":
            return str(f.get("boolean"))
        if ft == "date":
            return (f.get("date") or {}).get("start", "")
        return ""
    if t == "select":
        return (prop.get("select") or {}).get("name", "")
    if t == "multi_select":
        return ", ".join(s.get("name", "") for s in (prop.get("multi_select") or []))
    if t == "rich_text":
        return "".join(x.get("plain_text", "") for x in prop.get("rich_text", []))
    if t == "number":
        n = prop.get("number")
        return str(n) if n is not None else ""
    if t == "relation":
        rel = prop.get("relation") or []
        return f"{len(rel)} relation(s)" if rel else ""
    if t == "rollup":
        r = prop.get("rollup") or {}
        rt = r.get("type", "")
        if rt == "array":
            names = []
            for item in r.get("array", []):
                it = item.get("type", "")
                if it == "title":
                    names.append(
                        "".join(x.get("plain_text", "") for x in item.get("title", []))
                    )
                elif it == "rich_text":
                    names.append(
                        "".join(x.get("plain_text", "") for x in item.get("rich_text", []))
                    )
            return ", ".join(n for n in names if n)
        if rt == "number" and r.get("number") is not None:
            return str(r["number"])
    return ""


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

        # Extrai prioridade (no schema do Fernando, "Tipo" = prioridade real)
        priority_field = fields.get("priority", "Tipo")
        prioridade = _select_value(props.get(priority_field, {}))

        # Extrai urgencia — agora e FORMULA readOnly
        # (🔴 Atrasado / 🟠 Hoje / 🟡 Esta Semana / 🟢 Este Mes / ⚪ Sem Urgencia)
        urgency_field = fields.get("urgencia", fields.get("urgency", "Urgência Real"))
        urgencia = _read_any_text(props.get(urgency_field, {}))

        # Extrai deadline
        deadline_field = fields.get("deadline", "Deadline")
        deadline_prop = props.get(deadline_field, {})
        deadline = None
        if deadline_prop.get("type") == "date" and deadline_prop.get("date"):
            deadline = deadline_prop["date"].get("start")

        # Area (Grana / Juridico / Carreira / Network / Freelas / Mental)
        area = _select_value(props.get(fields.get("area", "Área"), {}))

        # Esforço (pode ser select pequeno/médio/grande, ou number)
        esforco = _read_any_text(props.get(fields.get("esforco", "Esforço"), {}))

        # Projeto (fórmula que resolve as relations, ou select, ou relation array)
        projeto = _read_any_text(props.get(fields.get("projeto", "Projeto"), {}))

        # Próximo Passo (rich_text)
        proximo_passo = _rich_text_value(
            props.get(fields.get("proximo_passo", "Próximo Passo"), {})
        )

        # Bloqueador (checkbox)
        bloqueador_field = fields.get("bloqueador", "Bloqueador?")
        bloqueador_prop = props.get(bloqueador_field, {})
        bloqueador = bool(bloqueador_prop.get("checkbox", False))

        return {
            "id": record.get("id", ""),
            "titulo": titulo,
            "status": status,
            "prioridade": prioridade,
            "urgencia": urgencia,
            "deadline": deadline,
            "area": area,
            "esforco": esforco,
            "projeto": projeto,
            "proximo_passo": proximo_passo,
            "bloqueador": bloqueador,
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
        """Analisa tarefas: atrasadas, por urgencia, por area, bloqueadores."""
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

        # Contagem por urgencia real (campo do Fernando)
        por_urgencia: dict[str, int] = {}
        for t in tarefas:
            u = t.get("urgencia") or "—"
            por_urgencia[u] = por_urgencia.get(u, 0) + 1

        # Contagem por area
        por_area: dict[str, int] = {}
        for t in tarefas:
            a = t.get("area") or "—"
            por_area[a] = por_area.get(a, 0) + 1

        # Contagem por projeto
        por_projeto: dict[str, int] = {}
        for t in tarefas:
            p = t.get("projeto") or ""
            if p:
                por_projeto[p] = por_projeto.get(p, 0) + 1

        # Bloqueadores ativos
        bloqueados = [t for t in tarefas if t.get("bloqueador")]

        # Por prioridade (Tipo: 🔥 Critico / ⚠️ Importante / 🧠 Estrategico)
        criticas = [t for t in tarefas if "Crítico" in (t.get("prioridade") or "")]

        return {
            "total": len(tarefas),
            "atrasadas": atrasadas,
            "hoje": hoje_list,
            "sem_deadline": sem_deadline,
            "por_urgencia": por_urgencia,
            "por_area": por_area,
            "por_projeto": por_projeto,
            "bloqueados": bloqueados,
            "criticas": criticas,
        }

    def _format_tarefa(self, t: dict) -> str:
        """Formata uma tarefa com metadados ricos para o contexto LLM."""
        parts = [t["titulo"]]
        if t.get("prioridade"):
            parts.append(f"[{t['prioridade']}]")
        if t.get("urgencia"):
            parts.append(f"({t['urgencia']})")
        if t.get("area"):
            parts.append(f"#{t['area']}")
        if t.get("projeto"):
            parts.append(f"@{t['projeto']}")
        if t.get("esforco"):
            parts.append(f"esforço={t['esforco']}")
        if t.get("deadline"):
            parts.append(f"deadline={t['deadline']}")
        if t.get("bloqueador"):
            parts.append("[BLOQUEADOR]")
        if t.get("proximo_passo"):
            # truncado pra nao inflar muito
            np = t["proximo_passo"]
            if len(np) > 80:
                np = np[:77] + "..."
            parts.append(f"→ {np}")
        return " ".join(parts)

    def context(self, data: dict, analysis: dict) -> str:
        """Gera texto de contexto para o briefing — rico em metadados."""
        lines = []
        lines.append(f"TAREFAS: {analysis['total']} ativas")

        # Breakdown por urgencia real
        urg = analysis.get("por_urgencia", {})
        if urg:
            ordem = ["🔴 Atrasado", "🟠 Hoje", "🟡 Esta Semana", "🟢 Este Mês", "⚪ Sem Urgência"]
            parts = []
            for k in ordem:
                if k in urg:
                    parts.append(f"{k}={urg[k]}")
            for k, v in urg.items():
                if k not in ordem:
                    parts.append(f"{k}={v}")
            lines.append("Urgência: " + " | ".join(parts))

        # Breakdown por area
        area = analysis.get("por_area", {})
        if area:
            parts = [f"{k}={v}" for k, v in sorted(area.items(), key=lambda x: -x[1])]
            lines.append("Área: " + " | ".join(parts))

        # Breakdown por projeto
        proj = analysis.get("por_projeto", {})
        if proj:
            parts = [f"{k}={v}" for k, v in sorted(proj.items(), key=lambda x: -x[1])[:8]]
            lines.append("Projeto: " + " | ".join(parts))

        # Bloqueadores (raro + importante)
        bloq = analysis.get("bloqueados", [])
        if bloq:
            lines.append(f"BLOQUEADORES ({len(bloq)}):")
            for t in bloq[:5]:
                lines.append(f"  - {self._format_tarefa(t)}")

        # Atrasadas com título completo
        if analysis["atrasadas"]:
            lines.append(f"ATRASADAS ({len(analysis['atrasadas'])}):")
            for t in analysis["atrasadas"][:10]:
                lines.append(f"  - {self._format_tarefa(t)}")

        # Hoje
        if analysis["hoje"]:
            lines.append(f"HOJE ({len(analysis['hoje'])}):")
            for t in analysis["hoje"]:
                lines.append(f"  - {self._format_tarefa(t)}")

        # Criticas com Tipo = 🔥 Critico
        crit = analysis.get("criticas", [])
        if crit and not any(c in analysis["atrasadas"] for c in crit):
            lines.append(f"CRÍTICAS ({len(crit)}):")
            for t in crit[:5]:
                lines.append(f"  - {self._format_tarefa(t)}")

        # Top 5 proximas (tem deadline mas nao atrasadas/hoje)
        com_deadline = [
            t for t in data["tarefas"]
            if t.get("deadline") and t not in analysis["atrasadas"] and t not in analysis["hoje"]
        ]
        top = com_deadline[:5]
        if top:
            lines.append("PRÓXIMAS:")
            for t in top:
                lines.append(f"  - {self._format_tarefa(t)}")

        return "\n".join(lines)
