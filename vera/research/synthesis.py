"""SynthesisEngine — sumarizacao LLM por topico."""

import logging

from vera.research.base import ResearchItem, ResearchResult

logger = logging.getLogger(__name__)


class SynthesisEngine:
    """Sintetiza resultados de research via LLM."""

    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def synthesize_topic(
        self,
        topic: str,
        items: list[ResearchItem],
        max_words: int = 80,
    ) -> str:
        """Recebe N itens de um topico, retorna 1 paragrafo sintetizado."""
        if not items:
            return ""

        n = len(items)
        items_text = "\n".join(
            f"- [{item.source_name}] {item.title}: {item.content[:200]}" for item in items[:10]
        )

        prompt = (
            f'Sintetize os seguintes {n} artigos sobre "{topic}" em um paragrafo '
            f"de no maximo {max_words} palavras. Foco em: o que mudou, o que e novo, "
            f"e o que requer atencao. Nao liste artigos individualmente. Cite fontes "
            f"apenas quando a atribuicao importa. Lingua: mesma do conteudo.\n\n"
            f"Artigos:\n{items_text}"
        )

        try:
            return await self.llm.generate(
                system_prompt="Voce e um analista que sintetiza noticias de forma concisa.",
                user_prompt=prompt,
                max_tokens=200,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning("Erro na sintese do topico '%s': %s", topic, e)
            # Fallback: lista simples
            titles = ", ".join(item.title[:50] for item in items[:3])
            return f"{topic}: {titles}"

    async def synthesize_pack(
        self,
        result: ResearchResult,
        topics: dict[str, list[ResearchItem]],
        max_words_per_topic: int = 80,
    ) -> str:
        """Sintetiza todos os topicos em texto para o briefing."""
        if not topics:
            return ""

        parts = []
        for topic_name, items in topics.items():
            if not items:
                continue
            synthesis = await self.synthesize_topic(topic_name, items, max_words_per_topic)
            if synthesis:
                parts.append(f"**{topic_name}** ({len(items)} novos): {synthesis}")

        return "\n\n".join(parts)
