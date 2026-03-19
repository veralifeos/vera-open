"""Database property schemas and sample data for Notion provisioning.

Each schema is a list of dicts with keys: name, type, and type-specific options.
schema_to_notion_properties() converts them to Notion API format.
"""

# ─── Database Schemas ────────────────────────────────────────────────────────

TASKS_SCHEMA = [
    {"name": "Name", "type": "title"},
    {
        "name": "Status",
        "type": "select",
        "options": ["To Do", "Doing", "Done", "Skip"],
    },
    {
        "name": "Tipo",
        "type": "select",
        "options": ["Importante", "Rotina", "Projeto"],
    },
    {"name": "Deadline", "type": "date"},
    {
        "name": "Área",
        "type": "select",
        "options": ["Carreira", "Freelas", "Network", "Mental", "Grana"],
    },
    {
        "name": "Urgência Real",
        "type": "select",
        "options": ["Atrasado", "Hoje", "Esta Semana", "Este Mês", "Sem Urgência"],
    },
    {"name": "Notas", "type": "rich_text"},
]

PIPELINE_SCHEMA = [
    {"name": "Empresa", "type": "title"},
    {"name": "Vaga", "type": "rich_text"},
    {
        "name": "Estágio",
        "type": "select",
        "options": [
            "Mapeada",
            "Aplicada",
            "Triagem",
            "Entrevista RH",
            "Entrevista Técnica",
            "Case/Teste",
            "Proposta",
            "Fechou",
        ],
    },
    {"name": "Fit", "type": "number"},
    {
        "name": "Prioridade",
        "type": "select",
        "options": ["A-Top", "B-Boa", "C-Backup"],
    },
    {"name": "Data Último Contato", "type": "date"},
    {"name": "Notas", "type": "rich_text"},
    {"name": "Próximo Passo", "type": "rich_text"},
]

CONTACTS_SCHEMA = [
    {"name": "Nome", "type": "title"},
    {"name": "Empresa", "type": "rich_text"},
    {
        "name": "Canal",
        "type": "select",
        "options": ["LinkedIn", "Email", "WhatsApp", "Telegram", "Presencial"],
    },
    {"name": "Último Contato", "type": "date"},
    {"name": "Notas", "type": "rich_text"},
]

CHECK_SEMANAL_SCHEMA = [
    {"name": "Semana", "type": "title"},
    {"name": "Energia", "type": "number"},
    {"name": "Vida Prática", "type": "number"},
    {"name": "Carreira", "type": "number"},
    {"name": "Sanidade", "type": "number"},
    {"name": "Highlight", "type": "rich_text"},
]

# Map domain name → (display title, schema)
DOMAIN_SCHEMAS = {
    "tasks": ("Vera — Tasks", TASKS_SCHEMA),
    "pipeline": ("Vera — Pipeline", PIPELINE_SCHEMA),
    "contacts": ("Vera — Contacts", CONTACTS_SCHEMA),
    "check_semanal": ("Vera — Check Semanal", CHECK_SEMANAL_SCHEMA),
}

# ─── Sample Data ─────────────────────────────────────────────────────────────

SAMPLE_TASKS = [
    {
        "Name": "Revisar config.yaml",
        "Status": "To Do",
        "Tipo": "Importante",
        "Área": "Carreira",
        "Urgência Real": "Hoje",
    },
    {
        "Name": "Atualizar LinkedIn",
        "Status": "To Do",
        "Tipo": "Rotina",
        "Área": "Network",
        "Urgência Real": "Esta Semana",
    },
]

SAMPLE_CONTACT = [
    {
        "Nome": "Exemplo — Contato",
        "Empresa": "Acme Corp",
        "Canal": "LinkedIn",
    },
]

SAMPLE_CHECK = [
    {
        "Semana": "S00 (exemplo)",
        "Energia": 7,
        "Vida Prática": 6,
        "Carreira": 5,
        "Sanidade": 8,
        "Highlight": "Primeiro check semanal!",
    },
]

SAMPLE_DATA = {
    "tasks": SAMPLE_TASKS,
    "contacts": SAMPLE_CONTACT,
    "check_semanal": SAMPLE_CHECK,
}

# ─── "Comece Aqui" Welcome Page Blocks ──────────────────────────────────────

COMECE_AQUI_BLOCKS = [
    {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Bem-vindo à Vera!"}}]
        },
    },
    {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": (
                            "A Vera é seu Life Operating System. "
                            "Ela lê seus dados do Notion, gera briefings diários via IA "
                            "e entrega no Telegram."
                        )
                    },
                }
            ]
        },
    },
    {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "Próximos passos"}}]
        },
    },
    {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [
                {"type": "text", "text": {"content": "Adicione suas tarefas no database Tasks"}}
            ],
            "checked": False,
        },
    },
    {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "Rode: python -m vera briefing --dry-run"},
                }
            ],
            "checked": False,
        },
    },
    {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "Configure o Telegram para receber briefings"},
                }
            ],
            "checked": False,
        },
    },
    {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "Rode: python -m vera doctor"},
                }
            ],
            "checked": False,
        },
    },
    {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": "Documentação completa: https://github.com/veralifeos/vera-open"
                    },
                }
            ]
        },
    },
]


# ─── Schema Converter ───────────────────────────────────────────────────────


def schema_to_notion_properties(schema: list[dict]) -> dict:
    """Convert our schema format to Notion API properties dict.

    Input: [{"name": "Status", "type": "select", "options": ["A", "B"]}, ...]
    Output: {"Status": {"select": {"options": [{"name": "A"}, {"name": "B"}]}}, ...}
    """
    properties: dict = {}
    for field in schema:
        name = field["name"]
        ftype = field["type"]

        if ftype == "title":
            properties[name] = {"title": {}}
        elif ftype == "rich_text":
            properties[name] = {"rich_text": {}}
        elif ftype == "number":
            properties[name] = {"number": {"format": "number"}}
        elif ftype == "date":
            properties[name] = {"date": {}}
        elif ftype == "select":
            options = [{"name": opt} for opt in field.get("options", [])]
            properties[name] = {"select": {"options": options}}
        elif ftype == "checkbox":
            properties[name] = {"checkbox": {}}

    return properties


def record_to_notion_properties(record: dict, schema: list[dict]) -> dict:
    """Convert a sample data dict to Notion page properties.

    Uses the schema to determine the correct Notion property type for each field.
    """
    schema_map = {f["name"]: f["type"] for f in schema}
    properties: dict = {}

    for key, value in record.items():
        ftype = schema_map.get(key)
        if not ftype:
            continue

        if ftype == "title":
            properties[key] = {
                "title": [{"type": "text", "text": {"content": str(value)}}]
            }
        elif ftype == "rich_text":
            properties[key] = {
                "rich_text": [{"type": "text", "text": {"content": str(value)}}]
            }
        elif ftype == "number":
            properties[key] = {"number": value}
        elif ftype == "date":
            properties[key] = {"date": {"start": str(value)}}
        elif ftype == "select":
            properties[key] = {"select": {"name": str(value)}}
        elif ftype == "checkbox":
            properties[key] = {"checkbox": bool(value)}

    return properties
