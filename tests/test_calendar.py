"""Testes da integracao Google Calendar."""

from unittest.mock import MagicMock

import pytest

from vera.integrations.calendar import (
    CalendarProvider,
    GoogleCalendarProvider,
    formatar_eventos_para_contexto,
)

# ─── Interface ─────────────────────────────────────────────────────────────────


def test_calendar_provider_e_abstrato():
    """CalendarProvider nao pode ser instanciado."""
    with pytest.raises(TypeError):
        CalendarProvider()


# ─── Formato de Eventos ───────────────────────────────────────────────────────


def test_formatar_eventos_vazio():
    """Lista vazia retorna string vazia."""
    assert formatar_eventos_para_contexto([]) == ""


def test_formatar_eventos_normais():
    """Eventos timed formatados com horario."""
    events = [
        {
            "title": "Call",
            "start": "09:00",
            "end": "10:00",
            "location": "Google Meet",
            "all_day": False,
        },
        {"title": "Treino", "start": "18:00", "end": "19:00", "location": None, "all_day": False},
    ]
    result = formatar_eventos_para_contexto(events)
    assert "AGENDA DO DIA" in result
    assert "09:00-10:00" in result
    assert "Call" in result
    assert "Google Meet" in result
    assert "18:00-19:00" in result
    assert "Treino" in result


def test_formatar_eventos_allday():
    """Eventos all-day formatados sem horario."""
    events = [
        {"title": "Feriado", "start": "all_day", "end": "", "location": None, "all_day": True},
    ]
    result = formatar_eventos_para_contexto(events)
    assert "dia inteiro" in result
    assert "Feriado" in result


# ─── Google Calendar Provider ────────────────────────────────────────────────


def _mock_events_response(items):
    """Cria mock do service Google Calendar."""
    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_list = MagicMock()
    mock_list.execute.return_value = {"items": items}
    mock_events.list.return_value = mock_list
    mock_service.events.return_value = mock_events
    return mock_service


def test_google_calendar_eventos_normais():
    """Busca e parseia eventos timed."""
    items = [
        {
            "summary": "Reuniao",
            "start": {"dateTime": "2026-03-06T09:00:00-03:00"},
            "end": {"dateTime": "2026-03-06T10:00:00-03:00"},
        },
    ]
    mock_service = _mock_events_response(items)

    provider = GoogleCalendarProvider("fake_creds", ["primary"])
    provider._service = mock_service

    events = provider._fetch_events_sync("America/Sao_Paulo")
    assert len(events) == 1
    assert events[0]["title"] == "Reuniao"
    assert events[0]["start"] == "09:00"
    assert events[0]["end"] == "10:00"
    assert events[0]["all_day"] is False


def test_google_calendar_evento_allday():
    """Parseia evento all-day."""
    items = [
        {
            "summary": "Feriado Nacional",
            "start": {"date": "2026-03-06"},
            "end": {"date": "2026-03-07"},
        },
    ]
    mock_service = _mock_events_response(items)

    provider = GoogleCalendarProvider("fake_creds", ["primary"])
    provider._service = mock_service

    events = provider._fetch_events_sync("America/Sao_Paulo")
    assert len(events) == 1
    assert events[0]["all_day"] is True
    assert events[0]["start"] == "all_day"


def test_google_calendar_vazio():
    """Calendario vazio retorna lista vazia."""
    mock_service = _mock_events_response([])

    provider = GoogleCalendarProvider("fake_creds", ["primary"])
    provider._service = mock_service

    events = provider._fetch_events_sync("America/Sao_Paulo")
    assert events == []


def test_google_calendar_multiplos_calendarios():
    """Busca em multiplos calendarios."""
    items = [
        {
            "summary": "Ev1",
            "start": {"dateTime": "2026-03-06T10:00:00-03:00"},
            "end": {"dateTime": "2026-03-06T11:00:00-03:00"},
        }
    ]

    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_list = MagicMock()
    mock_list.execute.return_value = {"items": items}
    mock_events.list.return_value = mock_list
    mock_service.events.return_value = mock_events

    provider = GoogleCalendarProvider("fake_creds", ["cal1", "cal2"])
    provider._service = mock_service

    events = provider._fetch_events_sync("America/Sao_Paulo")
    # Deve ter chamado list() para cada calendario
    assert mock_events.list.call_count == 2
    assert len(events) == 2  # Mesmo evento de cada calendario


def test_google_calendar_erro_auth():
    """Erro de auth e propagado."""
    provider = GoogleCalendarProvider("invalid_json", ["primary"])
    with pytest.raises(Exception):
        provider._get_service()


def test_google_calendar_ordena_allday_primeiro():
    """All-day events vem antes dos timed."""
    items = [
        {
            "summary": "Reuniao",
            "start": {"dateTime": "2026-03-06T09:00:00-03:00"},
            "end": {"dateTime": "2026-03-06T10:00:00-03:00"},
        },
        {
            "summary": "Feriado",
            "start": {"date": "2026-03-06"},
            "end": {"date": "2026-03-07"},
        },
    ]
    mock_service = _mock_events_response(items)

    provider = GoogleCalendarProvider("fake_creds", ["primary"])
    provider._service = mock_service

    events = provider._fetch_events_sync("America/Sao_Paulo")
    assert events[0]["all_day"] is True
    assert events[1]["all_day"] is False
