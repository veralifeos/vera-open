"""Job board sources — 9 fontes de vagas."""

import hashlib
import logging
import os
from datetime import datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from vera.research.base import ResearchItem
from vera.research.sources.base import Source

logger = logging.getLogger(__name__)

_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=2, min=2, max=8),
    "retry": retry_if_exception_type((httpx.HTTPError, TimeoutError)),
    "reraise": True,
}

_UA = "Vera/0.2 (+https://github.com/veralifeos/vera-open)"


def _job_id(title: str, company: str, source: str) -> str:
    normalized = f"{title.lower().strip()}|{company.lower().strip()}|{source}"
    return hashlib.md5(normalized.encode()).hexdigest()


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
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


class HimalayasSource(Source):
    """Himalayas — API publica, 20 jobs/req."""

    name = "himalayas"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        keywords = config.get("criteria", {}).get("keywords", [])
        query = " ".join(keywords[:3]) if keywords else "remote"
        url = f"https://himalayas.app/jobs/api?limit=20&q={query}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"User-Agent": _UA}, timeout=30)
            resp.raise_for_status()
            return resp.json().get("jobs", [])

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("title", "").strip()
        company = raw.get("companyName", raw.get("company_name", ""))
        if not title:
            return None
        return ResearchItem(
            id=_job_id(title, company, "himalayas"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("applicationUrl", raw.get("url", "")),
            source_name="Himalayas",
            published=_parse_date(raw.get("pubDate", raw.get("postedAt"))),
            content=raw.get("description", "")[:2000],
            metadata={
                "company": company,
                "location": raw.get("location", ""),
                "salary": raw.get("salary", ""),
            },
        )


class RemotiveSource(Source):
    """Remotive — API publica, ~2 req/min, 24h delay free."""

    name = "remotive"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        url = "https://remotive.com/api/remote-jobs?limit=20"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"User-Agent": _UA}, timeout=30)
            resp.raise_for_status()
            return resp.json().get("jobs", [])

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("title", "").strip()
        company = raw.get("company_name", "")
        if not title:
            return None
        return ResearchItem(
            id=_job_id(title, company, "remotive"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("url", ""),
            source_name="Remotive",
            published=_parse_date(raw.get("publication_date")),
            content=raw.get("description", "")[:2000],
            metadata={
                "company": company,
                "category": raw.get("category", ""),
                "salary": raw.get("salary", ""),
            },
        )


class RemoteOKSource(Source):
    """RemoteOK — JSON feed, 24h delay free."""

    name = "remoteok"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        url = "https://remoteok.com/api"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"User-Agent": _UA},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            # Primeiro item e metadata legal, pular
            return [j for j in data if isinstance(j, dict) and j.get("position")]

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("position", "").strip()
        company = raw.get("company", "")
        if not title:
            return None
        return ResearchItem(
            id=_job_id(title, company, "remoteok"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("url", ""),
            source_name="RemoteOK",
            published=_parse_date(raw.get("date")),
            content=raw.get("description", "")[:2000],
            metadata={
                "company": company,
                "tags": raw.get("tags", []),
                "salary_min": raw.get("salary_min"),
                "salary_max": raw.get("salary_max"),
                "location": raw.get("location", "Worldwide"),
            },
        )


class ArbeitnowSource(Source):
    """Arbeitnow — API publica, sem key, foco Europa + remoto."""

    name = "arbeitnow"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        url = "https://www.arbeitnow.com/api/job-board-api"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"User-Agent": _UA}, timeout=30)
            resp.raise_for_status()
            return resp.json().get("data", [])

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("title", "").strip()
        company = raw.get("company_name", "")
        if not title:
            return None
        return ResearchItem(
            id=_job_id(title, company, "arbeitnow"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("url", ""),
            source_name="Arbeitnow",
            published=_parse_date(raw.get("created_at")),
            content=raw.get("description", "")[:2000],
            metadata={
                "company": company,
                "location": raw.get("location", ""),
                "remote": raw.get("remote", False),
                "tags": raw.get("tags", []),
            },
        )


class JoobleSource(Source):
    """Jooble — API com key gratuita."""

    name = "jooble"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        sources_cfg = config.get("sources", {}).get("jooble", {})
        key_env = sources_cfg.get("api_key_env", "JOOBLE_API_KEY")
        api_key = os.environ.get(key_env, "")
        if not api_key:
            logger.info("Jooble: key nao encontrada (%s), desabilitando.", key_env)
            return []

        keywords = config.get("criteria", {}).get("keywords", [])
        query = " ".join(keywords[:3]) if keywords else "remote"
        url = f"https://jooble.org/api/{api_key}"
        payload = {"keywords": query, "location": "remote"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers={"User-Agent": _UA}, timeout=30)
            resp.raise_for_status()
            return resp.json().get("jobs", [])

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("title", "").strip()
        company = raw.get("company", "")
        if not title:
            return None
        return ResearchItem(
            id=_job_id(title, company, "jooble"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("link", ""),
            source_name="Jooble",
            published=_parse_date(raw.get("updated")),
            content=raw.get("snippet", "")[:2000],
            metadata={"company": company, "location": raw.get("location", "")},
        )


class JSearchSource(Source):
    """JSearch (RapidAPI) — LinkedIn/Indeed indireto."""

    name = "jsearch"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        sources_cfg = config.get("sources", {}).get("jsearch", {})
        key_env = sources_cfg.get("api_key_env", "RAPIDAPI_KEY")
        api_key = os.environ.get(key_env, "")
        if not api_key:
            logger.info("JSearch: key nao encontrada (%s), desabilitando.", key_env)
            return []

        keywords = config.get("criteria", {}).get("keywords", [])
        query = " ".join(keywords[:3]) if keywords else "remote"
        url = "https://jsearch.p.rapidapi.com/search"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                params={"query": query, "num_pages": "1"},
                headers={
                    "X-RapidAPI-Key": api_key,
                    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("job_title", "").strip()
        company = raw.get("employer_name", "")
        if not title:
            return None
        return ResearchItem(
            id=_job_id(title, company, "jsearch"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("job_apply_link", raw.get("job_google_link", "")),
            source_name="JSearch",
            published=_parse_date(raw.get("job_posted_at_datetime_utc")),
            content=raw.get("job_description", "")[:2000],
            metadata={
                "company": company,
                "location": raw.get("job_city", ""),
                "remote": raw.get("job_is_remote", False),
            },
        )


class GreenhouseSource(Source):
    """Greenhouse — API publica oficial, sem auth."""

    name = "greenhouse"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        boards = config.get("sources", {}).get("greenhouse", {}).get("boards", [])
        if not boards:
            return []

        all_jobs = []
        async with httpx.AsyncClient() as client:
            for board_token in boards:
                url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
                try:
                    resp = await client.get(url, timeout=30)
                    resp.raise_for_status()
                    jobs = resp.json().get("jobs", [])
                    for j in jobs:
                        j["_board"] = board_token
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.warning("Greenhouse board '%s': %s", board_token, e)
        return all_jobs

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("title", "").strip()
        if not title:
            return None
        company = raw.get("_board", "")
        location = ""
        if raw.get("location"):
            location = raw["location"].get("name", "")
        return ResearchItem(
            id=_job_id(title, company, "greenhouse"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("absolute_url", ""),
            source_name="Greenhouse",
            published=_parse_date(raw.get("updated_at")),
            content=raw.get("content", "")[:2000],
            metadata={"company": company, "location": location},
        )


class LeverSource(Source):
    """Lever — JSON publico, sem auth."""

    name = "lever"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        boards = config.get("sources", {}).get("lever", {}).get("boards", [])
        if not boards:
            return []

        all_jobs = []
        async with httpx.AsyncClient() as client:
            for company_slug in boards:
                url = f"https://api.lever.co/v0/postings/{company_slug}"
                try:
                    resp = await client.get(url, timeout=30)
                    resp.raise_for_status()
                    jobs = resp.json()
                    if isinstance(jobs, list):
                        all_jobs.extend(jobs)
                except Exception as e:
                    logger.warning("Lever board '%s': %s", company_slug, e)
        return all_jobs

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("text", "").strip()
        if not title:
            return None
        categories = raw.get("categories", {})
        company = categories.get("team", "")
        location = categories.get("location", "")
        return ResearchItem(
            id=_job_id(title, company or "lever", "lever"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("hostedUrl", raw.get("applyUrl", "")),
            source_name="Lever",
            published=None,  # Lever nao fornece date no listing
            content=raw.get("descriptionPlain", "")[:2000],
            metadata={"company": company, "location": location},
        )


class AshbySource(Source):
    """Ashby — API publica, sem auth."""

    name = "ashby"

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        boards = config.get("sources", {}).get("ashby", {}).get("boards", [])
        if not boards:
            return []

        all_jobs = []
        async with httpx.AsyncClient() as client:
            for board_slug in boards:
                url = f"https://api.ashbyhq.com/posting-api/job-board/{board_slug}"
                try:
                    resp = await client.get(url, timeout=30)
                    resp.raise_for_status()
                    jobs = resp.json().get("jobs", [])
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.warning("Ashby board '%s': %s", board_slug, e)
        return all_jobs

    def parse(self, raw: dict) -> ResearchItem | None:
        title = raw.get("title", "").strip()
        if not title:
            return None
        company = raw.get("organizationName", raw.get("departmentName", ""))
        location = raw.get("location", "")
        return ResearchItem(
            id=_job_id(title, company or "ashby", "ashby"),
            title=f"{company} — {title}" if company else title,
            url=raw.get("jobUrl", raw.get("applicationUrl", "")),
            source_name="Ashby",
            published=_parse_date(raw.get("publishedAt")),
            content=raw.get("descriptionPlain", raw.get("description", ""))[:2000],
            metadata={"company": company, "location": location},
        )


# Registry de todas as fontes
ALL_SOURCES: dict[str, type[Source]] = {
    "himalayas": HimalayasSource,
    "remotive": RemotiveSource,
    "remoteok": RemoteOKSource,
    "arbeitnow": ArbeitnowSource,
    "jooble": JoobleSource,
    "jsearch": JSearchSource,
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "ashby": AshbySource,
}
