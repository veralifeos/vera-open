"""Google Calendar integration — interface abstrata + provider Google.

CalendarProvider e uma interface abstrata para futuros provedores (Outlook, CalDAV).
GoogleCalendarProvider usa a API Google Calendar via service account ou OAuth2.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Formato padronizado de evento
# {"title": str, "start": str (HH:MM ou "all_day"), "end": str (HH:MM ou ""),
#  "location": str | None, "all_day": bool}


class CalendarProvider(ABC):
    """Interface para provedores de calendario."""

    @abstractmethod
    async def get_events_today(self, timezone: str) -> list[dict]:
        """Retorna eventos de hoje no formato padronizado."""
        ...


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar via OAuth2/service account."""

    def __init__(self, credentials_json: str, calendar_ids: list[str] | None = None):
        """Inicializa com credenciais JSON (service account ou OAuth2 token).

        Args:
            credentials_json: JSON string das credenciais ou path para o arquivo.
            calendar_ids: lista de calendar IDs para buscar. Default: ["primary"].
        """
        self._credentials_json = credentials_json
        self._calendar_ids = calendar_ids or ["primary"]
        self._service = None

    def _get_service(self):
        """Lazy init do service Google Calendar."""
        if self._service is not None:
            return self._service

        import json
        from pathlib import Path

        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        # Tenta como path primeiro, depois como JSON string
        creds_data = self._credentials_json
        path = Path(creds_data)
        if path.exists():
            creds_data = path.read_text(encoding="utf-8")

        info = json.loads(creds_data)
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        self._service = build("calendar", "v3", credentials=credentials)
        return self._service

    async def get_events_today(self, timezone: str) -> list[dict]:
        """Busca eventos de hoje em todos os calendarios configurados."""
        import asyncio

        # Google Calendar API e sync, roda em thread
        return await asyncio.to_thread(self._fetch_events_sync, timezone)

    def _fetch_events_sync(self, timezone: str) -> list[dict]:
        """Busca eventos (sync) — roda em thread."""
        service = self._get_service()
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        time_min = start_of_day.isoformat()
        time_max = end_of_day.isoformat()

        all_events = []
        for cal_id in self._calendar_ids:
            try:
                events_result = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy="startTime",
                        timeZone=timezone,
                    )
                    .execute()
                )
                for event in events_result.get("items", []):
                    parsed = self._parse_event(event, tz)
                    if parsed:
                        all_events.append(parsed)
            except Exception as e:
                logger.warning("Erro ao buscar calendario '%s': %s", cal_id, e)

        # Ordena: all_day primeiro, depois por horario
        all_events.sort(key=lambda e: (not e["all_day"], e["start"]))
        return all_events

    def _parse_event(self, event: dict, tz: ZoneInfo) -> dict | None:
        """Converte evento da API Google para formato padronizado."""
        title = event.get("summary", "Sem titulo")
        location = event.get("location")

        start_raw = event.get("start", {})
        end_raw = event.get("end", {})

        # All-day event
        if "date" in start_raw:
            return {
                "title": title,
                "start": "all_day",
                "end": "",
                "location": location,
                "all_day": True,
            }

        # Timed event
        start_str = start_raw.get("dateTime", "")
        end_str = end_raw.get("dateTime", "")

        try:
            start_dt = datetime.fromisoformat(start_str).astimezone(tz)
            end_dt = datetime.fromisoformat(end_str).astimezone(tz)
            return {
                "title": title,
                "start": start_dt.strftime("%H:%M"),
                "end": end_dt.strftime("%H:%M"),
                "location": location,
                "all_day": False,
            }
        except (ValueError, TypeError) as e:
            logger.warning("Erro ao parsear evento '%s': %s", title, e)
            return None


def formatar_eventos_para_contexto(events: list[dict]) -> str:
    """Formata lista de eventos para injecao no contexto do briefing."""
    if not events:
        return ""

    lines = ["=== AGENDA DO DIA ==="]
    for ev in events:
        if ev["all_day"]:
            lines.append(f"  (dia inteiro) — {ev['title']}")
        else:
            loc = f" ({ev['location']})" if ev.get("location") else ""
            lines.append(f"  {ev['start']}-{ev['end']} — {ev['title']}{loc}")

    return "\n".join(lines)
