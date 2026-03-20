"""CustomResearchPack — pack genérico e configurável via YAML.

O usuário define tudo no config/packs/custom.yaml (ou qualquer nome).
Suporta múltiplos tipos de fonte: RSS, web search (DuckDuckGo free) e URL scraping.
Zero código necessário — 100% configurável.

Exemplos de uso:
  - Editais de cultura em BH
  - Monitorar concorrentes
  - Novidades de um produto
  - Oportunidades de freela
  - Qualquer coisa que caiba em keywords + fontes
"""

import hashlib
import logging
from datetime import datetime, timezone

import httpx

from vera.research.base import ResearchItem, ResearchPack, ResearchResult
from vera.research.registry import registry
from vera.research.scoring import ScoringEngine, create_embedder

logger = logging.getLogger(__name__)

_UA = "Vera/0.4 (+https://github.com/veralifeos/vera-open)"


# ─── Source handlers ─────────────────────────────────────────────────────────


async def _fetch_rss(source_cfg: dict, config: dict) -> list[ResearchItem]:
    """Busca itens de um feed RSS."""
    try:
        import feedparser
    except ImportError:
        logger.warning("Custom pack: feedparser não instalado. `pip install feedparser`")
        return []

    url = source_cfg.get("url", "")
    name = source_cfg.get("name", url)
    if not url:
        return []

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"User-Agent": _UA}, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
    except Exception as e:
        logger.warning("Custom pack RSS '%s': %s", name, e)
        return []

    items = []
    for entry in feed.entries[:20]:
        title = entry.get("title", "").strip()
        if not title:
            continue

        content = entry.get("summary", entry.get("description", ""))
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        published = datetime(*pub[:6], tzinfo=timezone.utc) if pub else None
        link = entry.get("link", "")

        item_id = hashlib.md5(f"{link}|{title}".encode()).hexdigest()[:16]
        items.append(ResearchItem(
            id=item_id,
            title=title,
            url=link,
            source_name=name,
            published=published,
            content=content[:2000],
            metadata={"source_type": "rss", "feed_name": name},
        ))

    return items


async def _fetch_web_search(source_cfg: dict, config: dict) -> list[ResearchItem]:
    """Busca via DuckDuckGo Instant Answer API (gratuito, sem chave).

    Para buscas mais robustas, suporta também SerpAPI com chave opcional.
    """
    query_template = source_cfg.get("query", "")
    name = source_cfg.get("name", "Web Search")
    engine = source_cfg.get("engine", "duckduckgo")

    # Enriquece query com keywords do config se usar {keywords}
    keywords = config.get("keywords", [])
    kw_str = " OR ".join(f'"{k}"' for k in keywords[:5]) if keywords else ""
    query = query_template.replace("{keywords}", kw_str)

    if not query:
        return []

    items = []

    if engine == "duckduckgo":
        try:
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, headers={"User-Agent": _UA}, timeout=20)
                resp.raise_for_status()
                data = resp.json()

            # Related topics como resultados
            for topic in data.get("RelatedTopics", [])[:10]:
                if not isinstance(topic, dict):
                    continue
                text = topic.get("Text", "")
                link = topic.get("FirstURL", "")
                if not text or not link:
                    continue
                item_id = hashlib.md5(link.encode()).hexdigest()[:16]
                items.append(ResearchItem(
                    id=item_id,
                    title=text[:120],
                    url=link,
                    source_name=name,
                    published=None,
                    content=text[:2000],
                    metadata={"source_type": "web_search", "engine": "duckduckgo"},
                ))
        except Exception as e:
            logger.warning("Custom pack DuckDuckGo '%s': %s", query[:50], e)

    elif engine == "serpapi":
        import os
        api_key_env = source_cfg.get("api_key_env", "SERPAPI_KEY")
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            logger.warning("Custom pack: SerpAPI key não encontrada (%s)", api_key_env)
            return []
        try:
            url = "https://serpapi.com/search"
            params = {"q": query, "api_key": api_key, "num": "10", "format": "json"}
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

            for result in data.get("organic_results", [])[:10]:
                title = result.get("title", "")
                link = result.get("link", "")
                snippet = result.get("snippet", "")
                if not title:
                    continue
                item_id = hashlib.md5(link.encode()).hexdigest()[:16]
                items.append(ResearchItem(
                    id=item_id,
                    title=title,
                    url=link,
                    source_name=name,
                    published=None,
                    content=snippet[:2000],
                    metadata={"source_type": "web_search", "engine": "serpapi"},
                ))
        except Exception as e:
            logger.warning("Custom pack SerpAPI '%s': %s", query[:50], e)

    return items


async def _fetch_source(source_cfg: dict, config: dict) -> list[ResearchItem]:
    """Dispatcher por tipo de fonte."""
    source_type = source_cfg.get("type", "rss")
    if source_type == "rss":
        return await _fetch_rss(source_cfg, config)
    elif source_type == "web_search":
        return await _fetch_web_search(source_cfg, config)
    else:
        logger.warning("Custom pack: tipo de fonte '%s' não suportado", source_type)
        return []


# ─── Pack ────────────────────────────────────────────────────────────────────


class CustomResearchPack(ResearchPack):
    """Pack genérico configurável via YAML. Zero código necessário.

    Defina tudo em config/packs/custom.yaml (ou crie múltiplos:
    custom-editais.yaml, custom-concorrentes.yaml, etc.)
    """

    name = "custom"
    description = "Pack genérico configurável via YAML — busca qualquer coisa"

    def __init__(self):
        self._embedder = None
        self._embedder_initialized = False

    def _get_engine(self) -> ScoringEngine:
        if not self._embedder_initialized:
            self._embedder = create_embedder()
            self._embedder_initialized = True
        return ScoringEngine(embedder=self._embedder)

    async def collect(self, config: dict) -> list[ResearchItem]:
        """Coleta de todas as fontes configuradas."""
        sources = config.get("sources", [])
        if not sources:
            logger.warning("Custom pack: nenhuma fonte configurada em 'sources:'")
            return []

        all_items: list[ResearchItem] = []

        for source_cfg in sources:
            if not source_cfg.get("enabled", True):
                continue
            try:
                items = await _fetch_source(source_cfg, config)
                all_items.extend(items)
                logger.info(
                    "Custom pack: fonte '%s' → %d itens",
                    source_cfg.get("name", source_cfg.get("url", "?")),
                    len(items),
                )
            except Exception as e:
                logger.warning(
                    "Custom pack: fonte '%s' falhou: %s",
                    source_cfg.get("name", "?"), e,
                )

        return all_items

    async def score(self, items: list[ResearchItem], config: dict) -> list[ResearchItem]:
        """Scoring por keywords obrigatórias + opcionais + exclusão."""
        keywords_required = config.get("keywords", [])
        keywords_boost = config.get("keywords_boost", [])
        keywords_exclude = config.get("exclude_keywords", [])
        weights_cfg = config.get("scoring", {}).get("weights", {})
        kw_weight = weights_cfg.get("keyword", 0.5)
        emb_weight = weights_cfg.get("embedding", 0.5)

        engine = self._get_engine()
        reference = " ".join(keywords_required + keywords_boost)

        for item in items:
            text = f"{item.title} {item.content}".lower()

            # Exclusão imediata
            if any(ex.lower() in text for ex in keywords_exclude):
                item.score = 0.0
                continue

            # Keyword score — obrigatórias pesam mais
            kw_score = engine.score_keywords(item, keywords_required)

            # Boost por keywords secundárias
            if keywords_boost:
                boost_matched = sum(1 for k in keywords_boost if k.lower() in text)
                boost = min(boost_matched / len(keywords_boost), 1.0) * 0.2
                kw_score = min(kw_score + boost, 1.0)

            # Embedding similarity
            emb_score = engine.score_embedding(item, reference) if reference else 0.5

            item.score = engine.score_composite(
                kw_score, emb_score, weights=(kw_weight, emb_weight)
            )

        return items

    def format_for_briefing(self, result: ResearchResult) -> str:
        """Formata resultados para o briefing."""
        if not result.items:
            return ""

        if result.synthesis:
            return result.synthesis

        pack_label = result.pack_name.upper()
        n = len(result.items)
        top = sorted(result.items, key=lambda x: x.score, reverse=True)[:3]
        lines = [f"=== {pack_label} ({n} novo{'s' if n > 1 else ''}) ==="]
        for item in top:
            score_pct = f"{item.score:.0%}"
            source = item.source_name
            lines.append(f"• [{source}] {item.title[:80]} ({score_pct})")
            if item.url:
                lines.append(f"  {item.url}")
        return "\n".join(lines)


# ─── Auto-register ────────────────────────────────────────────────────────────

registry.register(CustomResearchPack)
__all__ = ["CustomResearchPack"]
