"""Financial sources — Finnhub, EDGAR, CoinGecko, DeFiLlama, news RSS."""

import hashlib
import logging
import os
from datetime import datetime

import httpx
from tenacity import retry

from vera.research.base import ResearchItem
from vera.research.retry import RETRY_KWARGS
from vera.research.sources.base import Source
from vera.research.sources.rss import RSSSource

logger = logging.getLogger(__name__)

_RETRY_KWARGS = RETRY_KWARGS


def _fin_id(title: str, source: str) -> str:
    return hashlib.md5(f"{title.lower().strip()}|{source}".encode()).hexdigest()


def _parse_date(date_str: str | int | None) -> datetime | None:
    if not date_str:
        return None
    if isinstance(date_str, int):
        try:
            return datetime.utcfromtimestamp(date_str)
        except (ValueError, OSError):
            return None
    if not isinstance(date_str, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class FinnhubSource(Source):
    """Finnhub — API primaria (earnings, company news). 60/min free."""

    name = "finnhub"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        key_env = config.get("api_keys", {}).get("finnhub_env", "FINNHUB_API_KEY")
        api_key = os.environ.get(key_env, "")
        if not api_key:
            logger.info("Finnhub: key nao encontrada (%s), desabilitando.", key_env)
            return []

        items = []
        watchlist = config.get("watchlist", {}).get("stocks", [])
        categories = config.get("categories", {})

        async with httpx.AsyncClient() as client:
            # Earnings calendar
            if categories.get("earnings", {}).get("enabled", True):
                try:
                    resp = await client.get(
                        "https://finnhub.io/api/v1/calendar/earnings",
                        params={"token": api_key},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    earnings = resp.json().get("earningsCalendar", [])
                    for e in earnings[:20]:
                        items.append({"_type": "earnings", **e})
                except Exception as ex:
                    logger.warning("Finnhub earnings: %s", ex)

            # Company news per ticker
            if categories.get("news", {}).get("enabled", True) and watchlist:
                from datetime import timedelta

                today = datetime.now().strftime("%Y-%m-%d")
                week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                for stock in watchlist[:5]:
                    ticker = stock.get("ticker", "")
                    if not ticker:
                        continue
                    try:
                        resp = await client.get(
                            "https://finnhub.io/api/v1/company-news",
                            params={
                                "symbol": ticker,
                                "from": week_ago,
                                "to": today,
                                "token": api_key,
                            },
                            timeout=30,
                        )
                        resp.raise_for_status()
                        news = resp.json()
                        for n in (news if isinstance(news, list) else [])[:5]:
                            items.append({"_type": "news", "_ticker": ticker, **n})
                    except Exception as ex:
                        logger.warning("Finnhub news %s: %s", ticker, ex)

        return items

    def parse(self, raw: dict) -> ResearchItem | None:
        item_type = raw.get("_type", "")

        if item_type == "earnings":
            symbol = raw.get("symbol", "")
            date = raw.get("date", "")
            if not symbol:
                return None
            estimate = raw.get("epsEstimate", "N/A")
            return ResearchItem(
                id=_fin_id(f"earnings-{symbol}-{date}", "finnhub"),
                title=f"Earnings: {symbol} ({date})",
                url="",
                source_name="Finnhub",
                published=_parse_date(date),
                content=f"EPS estimate: {estimate}. Quarter: {raw.get('quarter', 'N/A')}",
                metadata={"category": "earnings", "ticker": symbol},
            )

        if item_type == "news":
            headline = raw.get("headline", "").strip()
            if not headline:
                return None
            ticker = raw.get("_ticker", "")
            return ResearchItem(
                id=_fin_id(headline, "finnhub-news"),
                title=headline,
                url=raw.get("url", ""),
                source_name=f"Finnhub ({raw.get('source', '')})",
                published=None,
                content=raw.get("summary", "")[:2000],
                metadata={"category": "news", "ticker": ticker},
            )

        return None


class EdgarSource(Source):
    """SEC EDGAR via edgartools. Public domain, sem auth."""

    name = "edgar"

    async def fetch(self, config: dict) -> list[dict]:
        watchlist = config.get("watchlist", {}).get("stocks", [])
        if not watchlist:
            return []

        categories = config.get("categories", {})
        if not categories.get("sec_filings", {}).get("enabled", True):
            return []

        filing_types = categories.get("sec_filings", {}).get(
            "filing_types", ["10-K", "10-Q", "8-K"]
        )
        user_agent = config.get("edgar", {}).get("user_agent", "Vera Open vera.os.app@gmail.com")

        # Tenta importar edgartools
        try:
            from edgar import set_identity

            set_identity(user_agent)
        except ImportError:
            logger.info("edgartools nao instalado. Desabilitando EDGAR source.")
            return []

        items = []
        try:
            from edgar import Company

            for stock in watchlist[:5]:
                cik = stock.get("cik", "")
                ticker = stock.get("ticker", "")
                if not cik:
                    continue

                try:
                    company = Company(cik)
                    filings = company.get_filings(form=filing_types).latest(5)
                    for filing in filings:
                        items.append(
                            {
                                "_type": "filing",
                                "ticker": ticker,
                                "form": filing.form,
                                "date": str(filing.filing_date),
                                "description": getattr(filing, "description", ""),
                                "url": getattr(filing, "filing_url", ""),
                                "company": stock.get("name", ticker),
                            }
                        )
                except Exception as ex:
                    logger.warning("EDGAR %s: %s", ticker, ex)
        except Exception as ex:
            logger.warning("EDGAR import error: %s", ex)

        return items

    def parse(self, raw: dict) -> ResearchItem | None:
        form = raw.get("form", "")
        ticker = raw.get("ticker", "")
        company = raw.get("company", ticker)
        date = raw.get("date", "")
        if not form:
            return None

        return ResearchItem(
            id=_fin_id(f"{form}-{ticker}-{date}", "edgar"),
            title=f"SEC {form}: {company} ({ticker})",
            url=raw.get("url", ""),
            source_name="SEC EDGAR",
            published=_parse_date(date),
            content=raw.get("description", f"Filing {form} for {company}")[:2000],
            metadata={"category": "sec_filing", "ticker": ticker, "form": form},
        )


class CoinGeckoSource(Source):
    """CoinGecko — precos e variacao crypto. 30/min demo."""

    name = "coingecko"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        categories = config.get("categories", {})
        if not categories.get("crypto", {}).get("enabled", True):
            return []

        watchlist = config.get("watchlist", {}).get("crypto", [])
        if not watchlist:
            return []

        key_env = config.get("api_keys", {}).get("coingecko_env", "COINGECKO_API_KEY")
        api_key = os.environ.get(key_env, "")

        ids = ",".join(c.get("id", "") for c in watchlist if c.get("id"))
        if not ids:
            return []

        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        }
        headers = {}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

        items = []
        threshold = categories.get("crypto", {}).get("price_change_threshold", 5.0)
        for coin in watchlist:
            coin_id = coin.get("id", "")
            symbol = coin.get("symbol", coin_id.upper())
            if coin_id in data:
                price = data[coin_id].get("usd", 0)
                change = data[coin_id].get("usd_24h_change", 0)
                items.append(
                    {
                        "_type": "crypto",
                        "symbol": symbol,
                        "price": price,
                        "change_24h": change,
                        "threshold": threshold,
                    }
                )

        return items

    def parse(self, raw: dict) -> ResearchItem | None:
        symbol = raw.get("symbol", "")
        price = raw.get("price", 0)
        change = raw.get("change_24h", 0)
        if not symbol:
            return None

        direction = "+" if change >= 0 else ""
        content = f"{symbol}: ${price:,.2f} ({direction}{change:.1f}% 24h)"

        return ResearchItem(
            id=_fin_id(f"crypto-{symbol}-{datetime.now().strftime('%Y%m%d')}", "coingecko"),
            title=f"{symbol} ${price:,.2f} ({direction}{change:.1f}%)",
            url="",
            source_name="CoinGecko",
            published=None,
            content=content,
            metadata={
                "category": "crypto",
                "symbol": symbol,
                "price": price,
                "change_24h": change,
            },
        )


class DeFiLlamaSource(Source):
    """DeFiLlama — DeFi TVL e protocolos. Open-source, gratis."""

    name = "defillama"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        categories = config.get("categories", {})
        if not categories.get("crypto", {}).get("enabled", True):
            return []

        url = "https://api.llama.fi/protocols"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=30)
            resp.raise_for_status()
            protocols = resp.json()

        # Top 10 por TVL
        if isinstance(protocols, list):
            protocols.sort(key=lambda p: p.get("tvl") or 0, reverse=True)
            return [{"_type": "defi", **p} for p in protocols[:10]]
        return []

    def parse(self, raw: dict) -> ResearchItem | None:
        name = raw.get("name", "")
        tvl = raw.get("tvl") or 0
        change_1d = raw.get("change_1d") or 0
        if not name:
            return None

        return ResearchItem(
            id=_fin_id(f"defi-{name}-{datetime.now().strftime('%Y%m%d')}", "defillama"),
            title=f"DeFi: {name} — TVL ${tvl / 1e9:.1f}B" if tvl > 1e9 else f"DeFi: {name}",
            url=raw.get("url", ""),
            source_name="DeFiLlama",
            published=None,
            content=f"{name}: TVL ${tvl:,.0f}, 1d change: {change_1d or 0:.1f}%",
            metadata={"category": "defi", "name": name, "tvl": tvl},
        )


class FinancialNewsSource(Source):
    """RSS de fontes financeiras. Reutiliza RSSSource."""

    name = "financial_news"

    async def fetch(self, config: dict) -> list[dict]:
        categories = config.get("categories", {})
        news_cfg = categories.get("news", {})
        if not news_cfg.get("enabled", True):
            return []

        sources = news_cfg.get("sources", [])
        all_entries = []

        for src_cfg in sources:
            if src_cfg.get("type") != "rss":
                continue
            url = src_cfg.get("url", "")
            name = src_cfg.get("name", url)
            if not url:
                continue
            try:
                rss = RSSSource(url, name)
                entries = await rss.fetch(config)
                all_entries.extend(entries)
            except Exception as e:
                logger.warning("Financial news RSS '%s': %s", name, e)

        return all_entries

    def parse(self, raw: dict) -> ResearchItem | None:
        # Reutiliza parse do RSSSource
        rss = RSSSource("", "Financial News")
        item = rss.parse(raw)
        if item:
            item.metadata["category"] = "news"
        return item
