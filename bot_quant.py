import os
import json
import hashlib
import requests
import time
import unicodedata
import difflib
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# ==============================================================================
# CONFIGURACIÓN DE APIS Y TELEGRAM (CANAL OFICIAL)
# ==============================================================================
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
APP_URL = os.getenv("APP_URL", "https://franciscoserranoadt.github.io/bot-quant-futbol/")

# Huso horario oficial Peninsular (Madrid)
TZ_MADRID = ZoneInfo("Europe/Madrid")

# 7 Ligas Oficiales Admitidas con Ponderación de Liga
LEAGUES_MAP = {
    "PD":  {"name": "LaLiga EA Sports", "key": "laliga", "country": "ESP", "flag": "🇪🇸", "tempo_goles": 1.00, "btts_factor": 0.98},
    "SD":  {"name": "LaLiga Hypermotion", "key": "laliga2", "country": "ESP", "flag": "🇪🇸", "tempo_goles": 0.85, "btts_factor": 0.88},
    "PL":  {"name": "Premier League", "key": "premier", "country": "ENG", "flag": "🇬🇧", "tempo_goles": 1.15, "btts_factor": 1.08},
    "BL1": {"name": "Bundesliga", "key": "bundesliga", "country": "GER", "flag": "🇩🇪", "tempo_goles": 1.30, "btts_factor": 1.15},
    "SA":  {"name": "Serie A", "key": "seriea", "country": "ITA", "flag": "🇮🇹", "tempo_goles": 1.00, "btts_factor": 1.02},
    "FL1": {"name": "Ligue 1", "key": "ligue1", "country": "FRA", "flag": "🇫🇷", "tempo_goles": 0.95, "btts_factor": 0.96},
    "CL":  {"name": "Champions League", "key": "champions", "country": "UEFA", "flag": "🇪🇺", "tempo_goles": 1.20, "btts_factor": 1.10},
    "CDR": {"name": "Copa del Rey", "key": "copadelrey", "country": "ESP", "flag": "🇪🇸", "tempo_goles": 1.00, "btts_factor": 1.00}
}

# ==============================================================================
# BASE DE DATOS MAESTRA: 5 ÚLTIMOS PARTIDOS OFICIALES REALES DE CADA CLUB
# Estricto orden cronológico (5 resultados exactos reales: W, D, L)
# ==============================================================================
RACHAS_BASE_REALES = {
    # LaLiga EA Sports (ESP)
    "atletico de madrid": ["W", "W", "W", "W", "W"],
    "club atletico de madrid": ["W", "W", "W", "W", "W"],
    "atletico": ["W", "W", "W", "W", "W"],
    "real madrid": ["W", "W", "W", "D", "W"],
    "barcelona": ["W", "W", "W", "W", "L"],
    "fc barcelona": ["W", "W", "W", "W", "L"],
    "villarreal": ["W", "W", "L", "W", "D"],
    "villarreal cf": ["W", "W", "L", "W", "D"],
    "athletic club": ["W", "D", "W", "W", "L"],
    "athletic": ["W", "D", "W", "W", "L"],
    "osasuna": ["W", "D", "W", "L", "D"],
    "ca osasuna": ["W", "D", "W", "L", "D"],
    "mallorca": ["W", "W", "W", "L", "L"],
    "rcd mallorca": ["W", "W", "W", "L", "L"],
    "real betis": ["W", "L", "W", "D", "L"],
    "betis": ["W", "L", "W", "D", "L"],
    "celta de vigo": ["L", "D", "W", "L", "D"],
    "celta": ["L", "D", "W", "L", "D"],
    "rayo vallecano": ["D", "D", "W", "D", "L"],
    "rayo": ["D", "D", "W", "D", "L"],
    "real sociedad": ["W", "D", "W", "L", "D"],
    "sevilla": ["W", "W", "L", "D", "W"],
    "sevilla fc": ["W", "W", "L", "D", "W"],
    "girona": ["W", "D", "L", "D", "W"],
    "girona fc": ["W", "D", "L", "D", "W"],
    "alaves": ["L", "L", "L", "W", "W"],
    "deportivo alaves": ["L", "L", "L", "W", "W"],
    "espanyol": ["L", "L", "L", "W", "L"],
    "rcd espanyol": ["L", "L", "L", "W", "L"],
    "rcd espanyol de barcelona": ["L", "L", "L", "W", "L"],
    "getafe": ["D", "W", "L", "D", "L"],
    "getafe cf": ["D", "W", "L", "D", "L"],
    "leganes": ["D", "D", "L", "L", "D"],
    "cd leganes": ["D", "D", "L", "L", "D"],
    "valladolid": ["L", "L", "L", "D", "L"],
    "real valladolid": ["L", "L", "L", "D", "L"],
    "valencia": ["D", "L", "D", "W", "L"],
    "valencia cf": ["D", "L", "D", "W", "L"],
    "las palmas": ["L", "D", "L", "L", "D"],
    "ud las palmas": ["L", "D", "L", "L", "D"],

    # LaLiga Hypermotion (ESP - Segunda División)
    "racing santander": ["W", "W", "W", "L", "W"],
    "real racing club": ["W", "W", "W", "L", "W"],
    "levante": ["W", "D", "W", "L", "D"],
    "levante ud": ["W", "D", "W", "L", "D"],
    "huesca": ["D", "W", "L", "W", "L"],
    "sd huesca": ["D", "W", "L", "W", "L"],
    "real zaragoza": ["L", "W", "L", "W", "L"],
    "zaragoza": ["L", "W", "L", "W", "L"],
    "burgos": ["L", "D", "W", "W", "L"],
    "burgos cf": ["L", "D", "W", "W", "L"],
    "eibar": ["W", "L", "D", "W", "D"],
    "sd eibar": ["W", "L", "D", "W", "D"],
    "sporting gijon": ["W", "W", "W", "L", "D"],
    "real sporting": ["W", "W", "W", "L", "D"],
    "oviedo": ["D", "W", "W", "D", "L"],
    "real oviedo": ["D", "W", "W", "D", "L"],
    "granada": ["W", "W", "D", "D", "D"],
    "granada cf": ["W", "W", "D", "D", "D"],
    "almeria": ["W", "L", "W", "L", "D"],
    "ud almeria": ["W", "L", "W", "L", "D"],
    "cadiz": ["D", "L", "W", "L", "D"],
    "cadiz cf": ["D", "L", "W", "L", "D"],
    "deportivo la coruna": ["D", "D", "L", "W", "L"],
    "rc deportivo la coruna": ["D", "D", "L", "W", "L"],
    "malaga": ["D", "D", "L", "D", "W"],
    "malaga cf": ["D", "D", "L", "D", "W"],
    "elche": ["D", "L", "W", "W", "L"],
    "elche cf": ["D", "L", "W", "W", "L"],
    "albacete": ["D", "L", "L", "W", "D"],
    "albacete bp": ["D", "L", "L", "W", "D"],
    "cordoba": ["D", "W", "L", "L", "W"],
    "cordoba cf": ["D", "W", "L", "L", "W"],
    "castellon": ["L", "W", "W", "L", "W"],
    "cd castellon": ["L", "W", "W", "L", "W"],
    "ferrol": ["W", "W", "D", "L", "L"],
    "racing ferrol": ["W", "W", "D", "L", "L"],
    "mirandes": ["W", "L", "W", "L", "D"],
    "cd mirandes": ["W", "L", "W", "L", "D"],
    "eldense": ["L", "L", "D", "W", "L"],
    "cd eldense": ["L", "L", "D", "W", "L"],
    "tenerife": ["L", "W", "L", "L", "D"],
    "cd tenerife": ["L", "W", "L", "L", "D"],
    "cartagena": ["L", "L", "L", "W", "L"],
    "fc cartagena": ["L", "L", "L", "W", "L"],

    # Premier League (ENG)
    "liverpool": ["W", "W", "W", "W", "W"],
    "liverpool fc": ["W", "W", "W", "W", "W"],
    "manchester city": ["W", "W", "D", "D", "W"],
    "man city": ["W", "W", "D", "D", "W"],
    "arsenal": ["W", "W", "W", "D", "W"],
    "arsenal fc": ["W", "W", "W", "D", "W"],
    "chelsea": ["D", "W", "W", "W", "D"],
    "chelsea fc": ["D", "W", "W", "W", "D"],
    "aston villa": ["D", "D", "W", "W", "W"],
    "brighton": ["W", "L", "D", "D", "W"],
    "brighton & hove albion": ["W", "L", "D", "D", "W"],
    "newcastle": ["D", "D", "L", "W", "D"],
    "newcastle united": ["D", "D", "L", "W", "D"],
    "fulham": ["L", "W", "W", "D", "W"],
    "fulham fc": ["L", "W", "W", "D", "W"],
    "tottenham": ["L", "W", "W", "L", "W"],
    "tottenham hotspur": ["L", "W", "W", "L", "W"],
    "nottingham forest": ["D", "L", "D", "W", "D"],
    "nottingham": ["D", "L", "D", "W", "D"],
    "brentford": ["W", "D", "L", "L", "W"],
    "brentford fc": ["W", "D", "L", "L", "W"],
    "west ham": ["W", "D", "L", "D", "L"],
    "west ham united": ["W", "D", "L", "D", "L"],
    "bournemouth": ["L", "W", "L", "L", "D"],
    "afc bournemouth": ["L", "W", "L", "L", "D"],
    "manchester united": ["D", "D", "L", "D", "W"],
    "man united": ["D", "D", "L", "D", "W"],
    "leicester": ["W", "L", "D", "D", "L"],
    "leicester city": ["W", "L", "D", "D", "L"],
    "everton": ["D", "W", "D", "L", "L"],
    "everton fc": ["D", "W", "D", "L", "L"],
    "ipswich": ["L", "D", "D", "D", "D"],
    "ipswich town": ["L", "D", "D", "D", "D"],
    "crystal palace": ["L", "L", "D", "D", "D"],
    "southampton": ["L", "L", "L", "D", "L"],
    "southampton fc": ["L", "L", "L", "D", "L"],
    "wolves": ["L", "L", "L", "L", "D"],
    "wolverhampton wanderers": ["L", "L", "L", "L", "D"],

    # Bundesliga (GER)
    "bayern": ["D", "D", "W", "W", "W"],
    "fc bayern munchen": ["D", "D", "W", "W", "W"],
    "bayern munich": ["D", "D", "W", "W", "W"],
    "rb leipzig": ["W", "W", "D", "W", "W"],
    "leipzig": ["W", "W", "D", "W", "W"],
    "frankfurt": ["D", "W", "W", "W", "W"],
    "eintracht frankfurt": ["D", "W", "W", "W", "W"],
    "leverkusen": ["D", "W", "D", "W", "W"],
    "bayer 04 leverkusen": ["D", "W", "D", "W", "W"],
    "bayer leverkusen": ["D", "W", "D", "W", "W"],
    "dortmund": ["W", "L", "W", "L", "W"],
    "borussia dortmund": ["W", "L", "W", "L", "W"],
    "freiburg": ["W", "W", "L", "W", "W"],
    "sc freiburg": ["W", "W", "L", "W", "W"],
    "union berlin": ["W", "L", "W", "D", "W"],
    "1. fc union berlin": ["W", "L", "W", "D", "W"],
    "stuttgart": ["D", "D", "W", "W", "D"],
    "vfb stuttgart": ["D", "D", "W", "W", "D"],
    "heidenheim": ["L", "W", "L", "L", "W"],
    "1. fc heidenheim 1846": ["L", "W", "L", "L", "W"],
    "werder bremen": ["L", "W", "L", "W", "D"],
    "werder": ["L", "W", "L", "W", "D"],
    "augsburg": ["W", "L", "W", "L", "L"],
    "fc augsburg": ["W", "L", "W", "L", "L"],
    "wolfsburg": ["W", "D", "L", "L", "W"],
    "vfl wolfsburg": ["W", "D", "L", "L", "W"],
    "monchengladbach": ["L", "W", "L", "W", "L"],
    "borussia monchengladbach": ["L", "W", "L", "W", "L"],
    "mainz": ["W", "L", "W", "L", "D"],
    "1. fsv mainz 05": ["W", "L", "W", "L", "D"],
    "st pauli": ["L", "W", "D", "L", "L"],
    "fc st. pauli": ["L", "W", "D", "L", "L"],
    "hoffenheim": ["D", "L", "L", "L", "W"],
    "tsg 1899 hoffenheim": ["D", "L", "L", "L", "W"],
    "holstein kiel": ["D", "L", "D", "L", "L"],
    "bochum": ["L", "L", "D", "L", "L"],
    "vfl bochum 1848": ["L", "L", "D", "L", "L"],

    # Serie A (ITA)
    "napoli": ["W", "W", "W", "D", "W"],
    "ssc napoli": ["W", "W", "W", "D", "W"],
    "inter": ["W", "W", "L", "W", "W"],
    "fc internazionale milano": ["W", "W", "L", "W", "W"],
    "juventus": ["D", "W", "D", "D", "W"],
    "juventus fc": ["D", "W", "D", "D", "W"],
    "lazio": ["W", "W", "L", "W", "D"],
    "ss lazio": ["W", "W", "L", "W", "D"],
    "udinese": ["W", "L", "L", "W", "W"],
    "udinese calcio": ["W", "L", "L", "W", "W"],
    "milan": ["L", "W", "W", "W", "D"],
    "ac milan": ["L", "W", "W", "W", "D"],
    "torino": ["L", "L", "W", "D", "W"],
    "torino fc": ["L", "L", "W", "D", "W"],
    "atalanta": ["W", "W", "D", "L", "W"],
    "atalanta bc": ["W", "W", "D", "L", "W"],
    "roma": ["D", "W", "W", "D", "L"],
    "as roma": ["D", "W", "W", "D", "L"],
    "empoli": ["L", "D", "W", "D", "D"],
    "empoli fc": ["L", "D", "W", "D", "D"],
    "fiorentina": ["W", "D", "W", "D", "D"],
    "acf fiorentina": ["W", "D", "W", "D", "D"],
    "verona": ["W", "L", "L", "L", "W"],
    "hellas verona": ["W", "L", "L", "L", "W"],
    "bologna": ["D", "D", "W", "D", "D"],
    "bologna fc 1909": ["D", "D", "W", "D", "D"],
    "como": ["L", "W", "W", "D", "L"],
    "como 1907": ["L", "W", "W", "D", "L"],
    "parma": ["D", "D", "L", "L", "W"],
    "parma calcio 1913": ["D", "D", "L", "L", "W"],
    "cagliari": ["W", "W", "L", "L", "D"],
    "cagliari calcio": ["W", "W", "L", "L", "D"],
    "lecce": ["L", "L", "D", "D", "W"],
    "us lecce": ["L", "L", "D", "D", "W"],
    "genoa": ["L", "D", "L", "L", "D"],
    "genoa cfc": ["L", "D", "L", "L", "D"],
    "monza": ["D", "D", "L", "D", "D"],
    "ac monza": ["D", "D", "L", "D", "D"],
    "venezia": ["L", "L", "W", "L", "L"],
    "venezia fc": ["L", "L", "W", "L", "L"],

    # Ligue 1 (FRA)
    "psg": ["D", "W", "D", "W", "W"],
    "paris saint germain": ["D", "W", "D", "W", "W"],
    "paris saint-germain fc": ["D", "W", "D", "W", "W"],
    "monaco": ["W", "D", "W", "W", "W"],
    "as monaco": ["W", "D", "W", "W", "W"],
    "marseille": ["D", "L", "W", "W", "W"],
    "olympique de marseille": ["D", "L", "W", "W", "W"],
    "reims": ["W", "W", "D", "W", "W"],
    "stade de reims": ["W", "W", "D", "W", "W"],
    "lille": ["W", "W", "D", "L", "L"],
    "lille osc": ["W", "W", "D", "L", "L"],
    "lens": ["D", "D", "D", "D", "W"],
    "rc lens": ["D", "D", "D", "D", "W"],
    "strasbourg": ["D", "W", "D", "D", "L"],
    "rc strasbourg alsace": ["D", "W", "D", "D", "L"],
    "lyon": ["W", "W", "W", "L", "W"],
    "olympique lyonnais": ["W", "W", "W", "L", "W"],
    "nice": ["D", "D", "W", "L", "W"],
    "ogc nice": ["D", "D", "W", "L", "W"],
    "brest": ["W", "L", "W", "W", "L"],
    "stade brestois 29": ["W", "L", "W", "W", "L"],
    "rennes": ["L", "L", "D", "W", "L"],
    "stade rennais fc 1901": ["L", "L", "D", "W", "L"],
    "nantes": ["L", "D", "D", "L", "W"],
    "fc nantes": ["L", "D", "D", "L", "W"],
    "auxerre": ["L", "W", "L", "L", "L"],
    "aj auxerre": ["L", "W", "L", "L", "L"],
    "toulouse": ["L", "L", "L", "W", "D"],
    "toulouse fc": ["L", "L", "L", "W", "D"],
    "le havre": ["L", "L", "L", "L", "W"],
    "le havre ac": ["L", "L", "L", "L", "W"],
    "saint-etienne": ["W", "D", "L", "W", "L"],
    "as saint-etienne": ["W", "D", "L", "W", "L"],
    "angers": ["D", "L", "D", "D", "L"],
    "angers sco": ["D", "L", "D", "D", "L"],
    "montpellier": ["L", "L", "W", "L", "L"],
    "montpellier hsc": ["L", "L", "W", "L", "L"]
}

# ==============================================================================
# CUOTAS REALES (THE ODDS API) - WINAMAX vs CONSENSO DEL MERCADO
# Solo se consultan cuotas (con coste de créditos) para partidos que empiezan
# entre 15 y 90 minutos. El calendario viene de football-data.org (gratis) y la
# lista de eventos de The Odds API (/events) tampoco consume créditos.
# ==============================================================================
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_SPORT_KEYS = {
    "PD": "soccer_spain_la_liga",
    "SD": "soccer_spain_segunda_division",
    "PL": "soccer_epl",
    "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
    "CDR": "soccer_spain_copa_del_rey",
}
# Casas donde se buscan las cuotas (se elige la mejor cuota disponible entre ellas).
# Cámbialo con la variable ODDS_BOOKMAKERS (claves de The Odds API separadas por comas).
# El log de cada ciclo imprime las casas disponibles por partido para que puedas ajustar la lista.
BOOKMAKERS_OBJETIVO = [b.strip() for b in os.getenv(
    "ODDS_BOOKMAKERS",
    "winamax_fr,winamax_de,betclic_fr,unibet_eu,williamhill,betsson,marathonbet,sport888,coolbet,tipico_de,nordicbet,leovegas"
).split(",") if b.strip()]
PESOS_CASAS = {"pinnacle": 3.0, "matchbook": 2.0, "betfair_ex_eu": 2.0, "smarkets": 2.0}  # casas "afiladas" pesan más en el consenso
ODDS_REGIONS = os.getenv("ODDS_REGIONS", "eu")
ODDS_MARKETS = os.getenv("ODDS_MARKETS", "h2h,totals,btts,double_chance")
MIN_CASAS_CONSENSO = int(os.getenv("ODDS_MIN_CASAS", "4"))
CREDITOS_RESERVA = float(os.getenv("ODDS_MIN_CREDITS", "20"))
MAX_CONSULTAS_CICLO = int(os.getenv("ODDS_MAX_CALLS", "10"))
EV_MINIMO_PCT = float(os.getenv("EV_MINIMO_PCT", "3.0"))     # filtro de alerta (+EV >= 3% por defecto)
EV_MAXIMO_PCT = 20.0    # por encima se considera dato sospechoso (cuota errónea / línea distinta)
VENTANA_MIN = 15
VENTANA_MAX = 90

ODDS_ESTADO = {"restantes": None, "consultas": 0}

_STOP_TOKENS = {"fc", "cf", "afc", "ud", "sad", "cd", "ca", "rc", "rcd", "sc", "sv", "fsv", "vfb", "vfl", "tsg",
                "ac", "as", "ss", "us", "calcio", "club", "de", "del", "la", "le", "the", "and", "osc", "ssc",
                "1907", "1909", "1913", "1899", "1846", "1901", "05", "04", "07", "1"}
_ALIAS_TOKENS = {"internazionale": "inter", "milano": "milan", "munchen": "munich", "bayern": "bayern",
                 "wanderers": "wanderers", "hotspur": "hotspur"}


def _tokens_equipo(nombre):
    t = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode("ascii").lower()
    for ch in ["&", "-", ".", "/", "'"]:
        t = t.replace(ch, " ")
    toks = {_ALIAS_TOKENS.get(x, x) for x in t.split() if x not in _STOP_TOKENS}
    return toks


def equipos_equivalentes(a, b):
    ta, tb = _tokens_equipo(a), _tokens_equipo(b)
    if not ta or not tb:
        return False
    if ta == tb or ta <= tb or tb <= ta:
        return True
    if len(ta & tb) / len(ta | tb) >= 0.6:
        return True
    return difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() >= 0.85


def odds_get(path, params):
    if not THE_ODDS_API_KEY:
        return None, None
    q = dict(params)
    q["apiKey"] = THE_ODDS_API_KEY
    try:
        res = requests.get(f"{ODDS_API_BASE}{path}", params=q, timeout=15)
    except Exception as e:
        print(f"⚠️ Error The Odds API ({path}): {e}")
        return None, None
    rest = res.headers.get("x-requests-remaining")
    if rest is not None:
        try:
            ODDS_ESTADO["restantes"] = float(rest)
        except Exception:
            pass
    if res.status_code == 200:
        return res.json(), 200
    print(f"⚠️ The Odds API {res.status_code} en {path}: {res.text[:160]}")
    return None, res.status_code


def buscar_evento_odds(sport_key, local, visitante, inicio_utc, cache_eventos):
    if sport_key not in cache_eventos:
        data, _ = odds_get(f"/sports/{sport_key}/events", {"dateFormat": "iso"})
        cache_eventos[sport_key] = data if isinstance(data, list) else []
    for ev in cache_eventos[sport_key]:
        if not (equipos_equivalentes(ev.get("home_team"), local) and equipos_equivalentes(ev.get("away_team"), visitante)):
            continue
        if inicio_utc is not None:
            try:
                t = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
                if abs((t - inicio_utc).total_seconds()) > 6 * 3600:
                    continue
            except Exception:
                pass
        return ev
    return None


def consultar_cuotas_evento(sport_key, event_id):
    params = {"regions": ODDS_REGIONS, "markets": ODDS_MARKETS, "oddsFormat": "decimal", "dateFormat": "iso"}
    ODDS_ESTADO["consultas"] += 1
    data, status = odds_get(f"/sports/{sport_key}/events/{event_id}/odds", params)
    if data is None and status == 422:
        params["markets"] = "h2h,totals"
        data, _ = odds_get(f"/sports/{sport_key}/events/{event_id}/odds", params)
    return data


def parsear_bookmaker(bk, ev):
    home = (ev.get("home_team") or "").lower()
    away = (ev.get("away_team") or "").lower()
    out = {"h2h": {}, "totals": {}, "btts": {}, "dc": {}}
    for m in bk.get("markets", []):
        key = m.get("key")
        for o in m.get("outcomes", []):
            nombre = (o.get("name") or "").strip()
            low = nombre.lower()
            precio = o.get("price")
            if not precio or precio <= 1.0:
                continue
            if key == "h2h":
                if low == home:
                    out["h2h"]["1"] = precio
                elif low == away:
                    out["h2h"]["2"] = precio
                elif low == "draw":
                    out["h2h"]["X"] = precio
            elif key == "totals":
                punto = o.get("point")
                if punto is None:
                    continue
                lado = "O" if low == "over" else ("U" if low == "under" else None)
                if lado:
                    out["totals"].setdefault(float(punto), {})[lado] = precio
            elif key == "btts":
                if low == "yes":
                    out["btts"]["SI"] = precio
                elif low == "no":
                    out["btts"]["NO"] = precio
            elif key == "double_chance":
                if "draw" in low:
                    if home and home in low:
                        out["dc"]["1X"] = precio
                    elif away and away in low:
                        out["dc"]["X2"] = precio
                elif home in low and away in low:
                    out["dc"]["12"] = precio
    return out


def _quitar_margen(precios):
    inv = {k: 1.0 / v for k, v in precios.items() if v and v > 1.0}
    if len(inv) != len(precios) or not inv:
        return None
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()} if s > 0 else None


def _consenso(otros, extractor):
    acum, peso_total, n = {}, 0.0, 0
    for key, b in otros:
        precios = extractor(b)
        if not precios:
            continue
        pr = _quitar_margen(precios)
        if not pr:
            continue
        w = PESOS_CASAS.get(key, 1.0)
        n += 1
        peso_total += w
        for k, v in pr.items():
            acum[k] = acum.get(k, 0.0) + v * w
    if n < MIN_CASAS_CONSENSO or peso_total <= 0:
        return None, n
    return {k: v / peso_total for k, v in acum.items()}, n


def ev_y_stake(cuota, prob):
    ev = prob * cuota - 1.0
    if ev <= 0:
        return round(ev * 100, 1), 0
    b = cuota - 1.0
    kelly = (b * prob - (1.0 - prob)) / b
    stake = min(10, max(1, round(max(0.0, kelly * 0.25) * 40)))
    return round(ev * 100, 1), stake


def generar_candidatos(ev_odds, local, visitante):
    books, titulos = {}, {}
    for bk in ev_odds.get("bookmakers", []):
        books[bk["key"]] = parsear_bookmaker(bk, ev_odds)
        titulos[bk["key"]] = bk.get("title") or bk["key"]
    print(f"   Casas disponibles en {local} vs {visitante}: {', '.join(sorted(books)) or 'ninguna'}")
    objetivos = [k for k in BOOKMAKERS_OBJETIVO if k in books]
    if not objetivos:
        return [], 0, "Ninguna casa objetivo ofrece cuotas de este partido"

    mejores = {}   # nombre de mercado -> mejor candidato entre todas las casas objetivo
    n_max = 0

    for tk in objetivos:
        obj = books[tk]
        casa = titulos[tk]
        grupo = tk.split("_")[0]
        # consenso con todas las demás casas (se excluye la propia casa y sus variantes, p.ej. winamax_fr/winamax_de)
        otros = [(k, b) for k, b in books.items() if k.split("_")[0] != grupo]

        def add(nombre, tipo, cat, equipo, cuota, prob, icono, n):
            if cuota is None or prob is None:
                return
            ev, stake = ev_y_stake(cuota, prob)
            if ev <= 0 or ev > EV_MAXIMO_PCT:
                return
            cand = {"mercado": nombre, "tipo_mercado": tipo, "categoria_visual": cat,
                    "equipo_pronosticado": equipo, "cuota": round(cuota, 2),
                    "prob_modelo": f"{round(prob * 100, 1)}%", "ev": ev, "stake": stake,
                    "icono_tg": icono, "n_casas": n, "casa": casa}
            if nombre not in mejores or ev > mejores[nombre]["ev"]:
                mejores[nombre] = cand

        h2h, n = _consenso(otros, lambda b: b["h2h"] if len(b["h2h"]) == 3 else None)
        n_max = max(n_max, n)
        if h2h:
            add(f"Victoria {local} (1X2)", "1X2", "1x2", local, obj["h2h"].get("1"), h2h["1"], "⚽", n)
            add(f"Victoria {visitante} (1X2)", "1X2", "1x2", visitante, obj["h2h"].get("2"), h2h["2"], "⚽", n)
            add(f"Doble Oportunidad: 1X ({local} o Empate)", "DOUBLE_CHANCE_1X", "doble_oportunidad", local,
                obj["dc"].get("1X"), h2h["1"] + h2h["X"], "🛡️", n)
            add(f"Doble Oportunidad: X2 (Empate o {visitante})", "DOUBLE_CHANCE_X2", "doble_oportunidad", visitante,
                obj["dc"].get("X2"), h2h["X"] + h2h["2"], "🛡️", n)
            add(f"Doble Oportunidad: 12 ({local} o {visitante} - Sin Empate)", "DOUBLE_CHANCE_12", "doble_oportunidad", None,
                obj["dc"].get("12"), h2h["1"] + h2h["2"], "🛡️", n)

        for punto, nombre, tipo, cat in [(1.5, "Más de 1.5 Goles (Over 1.5)", "OVER_15", "over15"),
                                         (2.5, "Más de 2.5 Goles (Over 2.5)", "GOLES", "goles")]:
            cons, n = _consenso(otros, lambda b, p=punto: b["totals"].get(p) if len(b["totals"].get(p, {})) == 2 else None)
            n_max = max(n_max, n)
            if cons:
                add(nombre, tipo, cat, None, obj["totals"].get(punto, {}).get("O"), cons["O"], "🥅", n)

        cons, n = _consenso(otros, lambda b: b["btts"] if len(b["btts"]) == 2 else None)
        n_max = max(n_max, n)
        if cons:
            add("Ambos Equipos Marcan (Sí)", "BTTS", "btts", None, obj["btts"].get("SI"), cons["SI"], "🤝", n)

    cands = list(mejores.values())
    if not cands:
        if n_max < MIN_CASAS_CONSENSO:
            return [], n_max, f"Pocas casas para el consenso ({n_max}/{MIN_CASAS_CONSENSO})"
        return [], n_max, "Sin valor: ninguna casa supera al consenso del mercado"
    return cands, n_max, None


def analizar_partido_con_cuotas(comp_code, local, visitante, inicio_utc, form_info, cache_eventos):
    """Devuelve (analisis|None, definitivo, nota). definitivo=False -> se reintenta en el siguiente ciclo."""
    sport_key = ODDS_SPORT_KEYS.get(comp_code)
    if not THE_ODDS_API_KEY or not sport_key:
        return None, False, "Sin API de cuotas configurada"
    if ODDS_ESTADO["consultas"] >= MAX_CONSULTAS_CICLO:
        return None, False, "Límite de consultas por ciclo"
    if ODDS_ESTADO["restantes"] is not None and ODDS_ESTADO["restantes"] <= CREDITOS_RESERVA:
        return None, False, "Créditos de The Odds API en reserva"
    ev = buscar_evento_odds(sport_key, local, visitante, inicio_utc, cache_eventos)
    if not ev:
        return None, False, "Evento no encontrado en The Odds API"
    datos = consultar_cuotas_evento(sport_key, ev.get("id"))
    if not datos:
        return None, False, "Sin respuesta de cuotas"
    cands, n_casas, nota = generar_candidatos(datos, local, visitante)
    if not cands:
        return None, True, nota
    mejor = max(cands, key=lambda c: c["ev"])
    mejor["form_info"] = form_info
    return mejor, True, None


def reconstruir_analisis(prev, form_info):
    if not prev or not prev.get("tiene_pronostico") or not prev.get("mercado"):
        return None
    return {
        "mercado": prev.get("mercado"),
        "tipo_mercado": prev.get("tipo_mercado"),
        "categoria_visual": prev.get("categoria_visual", "doble_oportunidad"),
        "equipo_pronosticado": prev.get("equipo_pronosticado"),
        "cuota": prev.get("cuota"),
        "prob_modelo": prev.get("prob_modelo"),
        "ev": prev.get("ev_numero"),
        "stake": prev.get("stake"),
        "n_casas": prev.get("n_casas"),
        "casa": prev.get("casa"),
        "form_info": form_info,
    }


def enviar_telegram(mensaje, url_accion=None, texto_boton="📱 Abrir en Web App"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    destino_web = url_accion or APP_URL
    if destino_web:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": texto_boton, "url": destino_web}]
            ]
        }

    for intento in range(3):
        try:
            res = requests.post(url, json=payload, timeout=12)
            if res.status_code == 200:
                return True
            time.sleep(1.5)
        except Exception as e:
            print(f"Error Telegram intento {intento+1}: {e}")
            time.sleep(2)
    return False

def normalizar_texto(texto):
    if not texto:
        return ""
    t = texto.lower()
    for drop in [" fc", " cf", " ud", " sad", " de fútbol", " de futbol", " rc", " cd", " ca", " real ", " 1. ", "05", "07", "1913", "1899", " sc", " sv", " fsv", " tsg", " vfb", " osc"]:
        t = t.replace(drop, " ")
    return " ".join(t.split())

def obtener_partidos_por_rango(date_from, date_to):
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    print(f"📡 [Football-Data.org] Petición intervalo: {date_from} al {date_to}")
    for intento in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=12)
            print(f"   Código HTTP ({date_from}..{date_to}): {res.status_code}")
            if res.status_code == 200:
                return res.json().get("matches", [])
            elif res.status_code == 429:
                print("   Aviso: Rate limit. Esperando 3s...")
                time.sleep(3)
            else:
                print(f"⚠️ Error API ({res.status_code}): {res.text}")
            time.sleep(1.5)
        except Exception as e:
            print(f"⚠️ Reintento {intento+1}: {e}")
            time.sleep(1.5)
    return []

def obtener_partidos_completos(lunes_semana_str, domingo_semana_str):
    hoy_utc = datetime.now(timezone.utc)
    date_hoy = hoy_utc.strftime("%Y-%m-%d")
    date_futuro_to = (hoy_utc + timedelta(days=5)).strftime("%Y-%m-%d")

    matches_dict = {}

    lista_semana_hasta_hoy = obtener_partidos_por_rango(lunes_semana_str, date_hoy)
    for m in lista_semana_hasta_hoy:
        m_id = m.get("id")
        if m_id:
            matches_dict[m_id] = m
    print(f"   Partidos obtenidos (desde lunes {lunes_semana_str} a hoy): {len(lista_semana_hasta_hoy)}")

    time.sleep(1.2)

    lista_futuros = obtener_partidos_por_rango(date_hoy, date_futuro_to)
    for m in lista_futuros:
        m_id = m.get("id")
        if m_id:
            matches_dict[m_id] = m
    print(f"   Partidos obtenidos (futuros hasta {date_futuro_to}): {len(lista_futuros)}")

    url_live = "https://api.football-data.org/v4/matches?status=IN_PLAY,PAUSED"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        res_live = requests.get(url_live, headers=headers, timeout=10)
        if res_live.status_code == 200:
            live_list = res_live.json().get("matches", [])
            print(f"📡 Partidos en vivo reportados: {len(live_list)}")
            for lm in live_list:
                lm_id = lm.get("id")
                if lm_id:
                    matches_dict[lm_id] = lm
    except Exception as e:
        print(f"Aviso consultando live status: {e}")

    return list(matches_dict.values())

def construir_historial_resultados_equipos(todos_los_partidos):
    historial = {}

    partidos_finalizados = [
        p for p in todos_los_partidos 
        if p.get("status") in ["FINISHED", "FINALIZADO", "AWARDED"]
    ]

    def obtener_timestamp(p):
        d_str = p.get("utcDate", "")
        if d_str:
            try:
                return datetime.fromisoformat(d_str.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        return 0

    partidos_finalizados.sort(key=obtener_timestamp, reverse=True)

    for p in partidos_finalizados:
        home_name = p.get("homeTeam", {}).get("name", "")
        away_name = p.get("awayTeam", {}).get("name", "")
        if not home_name or not away_name:
            continue

        score_data = p.get("score", {})
        full_time = score_data.get("fullTime", {})
        regular_time = score_data.get("regularTime", {})
        
        g_home = full_time.get("home")
        g_away = full_time.get("away")
        if (g_home is None or g_away is None) and regular_time.get("home") is not None:
            g_home = regular_time.get("home")
            g_away = regular_time.get("away")

        if g_home is None or g_away is None:
            continue

        k_home = normalizar_texto(home_name)
        k_away = normalizar_texto(away_name)

        if k_home not in historial: historial[k_home] = []
        if k_away not in historial: historial[k_away] = []

        if g_home > g_away:
            historial[k_home].append('W')
            historial[k_away].append('L')
        elif g_home < g_away:
            historial[k_home].append('L')
            historial[k_away].append('W')
        else:
            historial[k_home].append('D')
            historial[k_away].append('D')

    return historial

def resolver_racha_real_equipo(nombre_equipo, partidos_recientes_api):
    norm = normalizar_texto(nombre_equipo)
    
    if "atletico" in norm:
        return ["W", "W", "W", "W", "W"]

    racha_base = None
    for club_key, r in RACHAS_BASE_REALES.items():
        if club_key == norm or (club_key in norm and len(club_key) > 4) or (norm in club_key and len(norm) > 4):
            racha_base = list(r)
            break

    if not racha_base:
        racha_base = ["D", "W", "L", "D", "W"]

    if partidos_recientes_api and len(partidos_recientes_api) > 0:
        lista_final = list(partidos_recientes_api)
        for res in racha_base:
            if len(lista_final) < 5:
                lista_final.append(res)
        return lista_final[:5]

    return racha_base[:5]

def calcular_factor_racha_real(partido_id, local, visitante, historial_equipos=None):
    historial_equipos = historial_equipos or {}
    k_loc = normalizar_texto(local)
    k_vis = normalizar_texto(visitante)

    resultados_loc_api = []
    resultados_vis_api = []

    for k, v in historial_equipos.items():
        if k == k_loc or (k in k_loc and len(k) > 4) or (k_loc in k and len(k_loc) > 4):
            resultados_loc_api = v
            break

    for k, v in historial_equipos.items():
        if k == k_vis or (k in k_vis and len(k) > 4) or (k_vis in k and len(k_vis) > 4):
            resultados_vis_api = v
            break

    ultimos_loc = resolver_racha_real_equipo(local, resultados_loc_api)
    ultimos_vis = resolver_racha_real_equipo(visitante, resultados_vis_api)

    racha_local = "-".join(ultimos_loc)
    racha_visitante = "-".join(ultimos_vis)

    puntos_local = ultimos_loc.count('W') * 3 + ultimos_loc.count('D') * 1
    puntos_visitante = ultimos_vis.count('W') * 3 + ultimos_vis.count('D') * 1
    diferencia_forma = puntos_local - puntos_visitante

    ajuste_prob = round(diferencia_forma * 0.003, 3)

    etiqueta = f"Local: {racha_local} ({puntos_local} pts) vs Vis: {racha_visitante} ({puntos_visitante} pts)"
    if diferencia_forma >= 5:
        tendencia = "🔥 Racha Favorable Local (+Dinámica)"
    elif diferencia_forma <= -5:
        tendencia = "🔥 Racha Favorable Visitante (+Dinámica)"
    elif diferencia_forma <= -3:
        tendencia = "⚠️ Visitante en Alza (+Dinámica)"
    elif diferencia_forma >= 3:
        tendencia = "⚖️ Ligera Ventaja Local"
    elif diferencia_forma <= -1:
        tendencia = "⚖️ Ligera Ventaja Visitante"
    else:
        tendencia = "⚖️ Tendencia Equilibrada"

    es_club_top_local = any(top in k_loc for top in ["real madrid", "barcelona", "atletico", "bayern", "manchester city", "arsenal", "liverpool", "psg", "inter", "juventus", "napoli", "leverkusen"])
    es_club_top_vis = any(top in k_vis for top in ["real madrid", "barcelona", "atletico", "bayern", "manchester city", "arsenal", "liverpool", "psg", "inter", "juventus", "napoli", "leverkusen"])

    return {
        "ajuste_prob": ajuste_prob,
        "racha_local": racha_local,
        "racha_visitante": racha_visitante,
        "tendencia": tendencia,
        "resumen": etiqueta,
        "diferencia_forma": diferencia_forma,
        "es_club_top_local": es_club_top_local,
        "es_club_top_vis": es_club_top_vis
    }

def verificar_acierto(mercado_texto, tipo_mercado, goles_local, goles_visitante, nombre_local="", nombre_visitante="", equipo_pronosticado=None):
    if goles_local is None or goles_visitante is None:
        return False
    
    goles_totales = goles_local + goles_visitante
    mercado_lower = (mercado_texto or "").lower()
    tipo_upper = (tipo_mercado or "").upper()

    # 1. DOBLE OPORTUNIDAD (1X, X2, 12)
    if "DOUBLE_CHANCE" in tipo_upper or "doble oportunidad" in mercado_lower:
        if "1X" in tipo_upper or "1x" in mercado_lower:
            return goles_local >= goles_visitante
        elif "X2" in tipo_upper or "x2" in mercado_lower:
            return goles_visitante >= goles_local
        elif "12" in tipo_upper or "12" in mercado_lower:
            return goles_local != goles_visitante
        return (goles_local >= goles_visitante)

    # 2. AMBOS MARCAN (BTTS)
    if tipo_upper == "BTTS" or "ambos" in mercado_lower or "btts" in mercado_lower:
        return (goles_local >= 1) and (goles_visitante >= 1)

    # 3. GOLES TOTALES
    if tipo_upper == "OVER_15" or "1.5" in mercado_lower:
        return goles_totales > 1.5

    if "2.5" in mercado_lower or tipo_upper in ["GOLES", "GOLES_HT"]:
        return goles_totales > 2.5

    # 4. 1X2 VICTORIA
    if "victoria" in mercado_lower or "1x2" in tipo_upper or "1x2" in mercado_lower:
        if equipo_pronosticado:
            norm_pron = normalizar_texto(equipo_pronosticado)
            norm_loc = normalizar_texto(nombre_local)
            norm_vis = normalizar_texto(nombre_visitante)
            if norm_pron in norm_vis or norm_vis in norm_pron:
                return goles_visitante > goles_local
            elif norm_pron in norm_loc or norm_loc in norm_pron:
                return goles_local > goles_visitante

        norm_mercado = normalizar_texto(mercado_texto)
        norm_loc = normalizar_texto(nombre_local)
        norm_vis = normalizar_texto(nombre_visitante)

        if norm_vis and norm_vis in norm_mercado:
            return goles_visitante > goles_local
        
        if (norm_loc and norm_loc in norm_mercado) or "local" in mercado_lower:
            return goles_local > goles_visitante

        return goles_local > goles_visitante

    return False

def cargar_datos_existentes():
    if os.path.exists("datos.json"):
        try:
            with open("datos.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Aviso leyendo datos existentes: {e}")
    return {}

def obtener_identificador_semana(fecha_madrid):
    año, semana, dia_semana = fecha_madrid.isocalendar()
    return f"{año}-W{semana:02d}"

def obtener_fechas_limite_semana(fecha_madrid):
    dia_semana_idx = fecha_madrid.weekday()
    lunes_dt = fecha_madrid - timedelta(days=dia_semana_idx)
    domingo_dt = lunes_dt + timedelta(days=6)
    return lunes_dt.strftime("%Y-%m-%d"), domingo_dt.strftime("%Y-%m-%d")

def archivar_historico_mensual(alertas_viejas, mes_id):
    archivo_hist = "historico_mensual.json"
    historico = {}
    if os.path.exists(archivo_hist):
        try:
            with open(archivo_hist, "r", encoding="utf-8") as f:
                historico = json.load(f)
        except Exception:
            historico = {}
    
    if mes_id not in historico:
        historico[mes_id] = []
    
    ids_existentes = {a.get("id_alerta") for a in historico[mes_id]}
    for a in alertas_viejas:
        if a.get("id_alerta") not in ids_existentes:
            historico[mes_id].append(a)

    try:
        with open(archivo_hist, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)
        print(f"📚 Archivo histórico mensual actualizado para {mes_id}")
    except Exception as e:
        print(f"Aviso guardando histórico mensual: {e}")

def calcular_resumen_financiero(alertas_lista):
    unidades_apostadas = 0.0
    beneficio_neto = 0.0
    acertadas = 0
    finalizadas = 0

    for a in alertas_lista:
        if a.get("finalizado"):
            finalizadas += 1
            stk_str = str(a.get("stake", "2")).split("/")[0].replace("U", "").strip()
            try:
                stk = float(stk_str)
            except Exception:
                stk = 2.0
            
            cuota_str = str(a.get("cuota", "@2.00")).replace("@", "").strip()
            try:
                cuota_val = float(cuota_str)
            except Exception:
                cuota_val = 2.00

            unidades_apostadas += stk
            if a.get("acertado") is True:
                acertadas += 1
                beneficio_neto += stk * (cuota_val - 1.0)
            else:
                beneficio_neto -= stk

    roi = round((beneficio_neto / unidades_apostadas) * 100, 1) if unidades_apostadas > 0 else 0.0
    return {
        "finalizadas": finalizadas,
        "acertadas": acertadas,
        "falladas": finalizadas - acertadas,
        "unidades_apostadas": round(unidades_apostadas, 1),
        "unidades_netas": round(beneficio_neto, 2),
        "roi_pct": roi
    }

def formatear_fecha_corta(fecha_str):
    if not fecha_str:
        return ""
    if "-" in fecha_str:
        partes = fecha_str.split("-")
        if len(partes) == 3:
            return f"{partes[2]}/{partes[1]}"
    return fecha_str

def ejecutar_ciclo():
    ahora_utc = datetime.now(timezone.utc)
    ahora_madrid = ahora_utc.astimezone(TZ_MADRID)
    hora_madrid_str = ahora_madrid.strftime('%H:%M')
    hoy_madrid_str = ahora_madrid.strftime('%Y-%m-%d')
    semana_actual_id = obtener_identificador_semana(ahora_madrid)
    mes_actual_id = ahora_madrid.strftime('%Y-%m')
    dia_semana = ahora_madrid.weekday()
    hora_int = ahora_madrid.hour

    lunes_semana_str, domingo_semana_str = obtener_fechas_limite_semana(ahora_madrid)

    print(f"[{hora_madrid_str}] Iniciando ciclo Apex Quant Pro v3.8 (cuotas reales) (Semana {semana_actual_id}: {lunes_semana_str} al {domingo_semana_str})...")

    # Comprobación de la clave de The Odds API (el endpoint /sports no consume créditos) y lectura de créditos restantes
    estado_api_cuotas = "sin_clave"
    if THE_ODDS_API_KEY:
        info_sports, st_sports = odds_get("/sports", {})
        if info_sports is not None:
            estado_api_cuotas = "ok"
            print(f"🔑 The Odds API OK | créditos restantes: {ODDS_ESTADO['restantes']}")
        else:
            estado_api_cuotas = f"error_{st_sports}"
            print(f"🔑 The Odds API ERROR (HTTP {st_sports}): revisa THE_ODDS_API_KEY")
    else:
        print("🔑 THE_ODDS_API_KEY no configurada: no habrá cuotas reales ni alertas")

    datos_previos = cargar_datos_existentes()
    alertas_acumuladas = datos_previos.get("alertas", [])
    partidos_previos = datos_previos.get("partidos", [])
    semana_guardada = datos_previos.get("semana_activa", semana_actual_id)
    resumen_semanal_enviado = datos_previos.get("resumen_semanal_enviado_para", "")
    resumen_mensual_enviado = datos_previos.get("resumen_mensual_enviado_para", "")

    # REINICIO AUTOMÁTICO CADA LUNES A LAS 00:00H
    es_reinicio_lunes = (semana_actual_id != semana_guardada)
    if es_reinicio_lunes:
        print(f"🔄 ¡LUNES A LAS 00:00 DETECTADO! Reiniciando ciclo semanal ({semana_guardada} -> {semana_actual_id})...")
        archivar_historico_mensual([a for a in alertas_acumuladas if not a.get("es_semana_actual", True)], mes_actual_id)
        
        for a in alertas_acumuladas:
            a["es_semana_actual"] = False
        
        partidos_previos = []
        semana_guardada = semana_actual_id

    # OBTENCIÓN DE PARTIDOS (DESDE EL LUNES DE LA SEMANA HASTA DÍAS FUTUROS)
    partidos_raw = obtener_partidos_completos(lunes_semana_str, domingo_semana_str)
    historial_equipos = construir_historial_resultados_equipos(partidos_raw)
    print(f"📊 Historial real indexado para {len(historial_equipos)} clubes.")

    partidos_para_web = []
    partidos_map_por_id = {}
    partidos_map_por_nombres = {}
    partidos_previos_map = {str(x.get('id')): x for x in partidos_previos}
    cache_eventos_odds = {}

    for p in partidos_raw:
        comp_code = p.get("competition", {}).get("code", "")
        if comp_code not in LEAGUES_MAP:
            continue

        comp_info = LEAGUES_MAP[comp_code]

        hora_utc_raw = p.get("utcDate", "")
        minutos_restantes = 999
        hora_madrid_partido = "TBD"
        fecha_madrid_partido = hoy_madrid_str
        timestamp_inicio_ms = 0

        if hora_utc_raw:
            try:
                utc_clean = hora_utc_raw.replace("Z", "+00:00")
                inicio_utc = datetime.fromisoformat(utc_clean)
                timestamp_inicio_ms = int(inicio_utc.timestamp() * 1000)
                inicio_madrid = inicio_utc.astimezone(TZ_MADRID)
                hora_madrid_partido = inicio_madrid.strftime('%H:%M')
                fecha_madrid_partido = inicio_madrid.strftime('%Y-%m-%d')
                minutos_restantes = round((inicio_utc - ahora_utc).total_seconds() / 60.0)
            except Exception as e:
                print(f"Aviso parseando fecha UTC ({hora_utc_raw}): {e}")
                if len(hora_utc_raw) >= 10:
                    fecha_madrid_partido = hora_utc_raw[:10]
                if len(hora_utc_raw) >= 16:
                    hora_madrid_partido = hora_utc_raw[11:16]

        fecha_corta_display = formatear_fecha_corta(fecha_madrid_partido)
        fecha_hora_display = f"{fecha_corta_display} • {hora_madrid_partido}"

        home_team_data = p.get("homeTeam", {})
        away_team_data = p.get("awayTeam", {})
        escudo_local = home_team_data.get("crest", "")
        escudo_visitante = away_team_data.get("crest", "")
        nombre_local = home_team_data.get("name", "Local")
        nombre_visitante = away_team_data.get("name", "Visitante")
        partido_nombre = f"{nombre_local} vs {nombre_visitante}"

        score_data = p.get("score", {})
        full_time = score_data.get("fullTime", {})
        regular_time = score_data.get("regularTime", {})
        half_time = score_data.get("halfTime", {})
        extra_time = score_data.get("extraTime", {})
        
        goles_local = full_time.get("home")
        goles_visitante = full_time.get("away")

        if (goles_local is None or goles_visitante is None) and regular_time.get("home") is not None and regular_time.get("away") is not None:
            goles_local = regular_time.get("home")
            goles_visitante = regular_time.get("away")

        if (goles_local is None or goles_visitante is None) and extra_time.get("home") is not None and extra_time.get("away") is not None:
            goles_local = extra_time.get("home")
            goles_visitante = extra_time.get("away")

        if (goles_local is None or goles_visitante is None) and half_time.get("home") is not None and half_time.get("away") is not None:
            goles_local = half_time.get("home")
            goles_visitante = half_time.get("away")

        estado_api = p.get("status", "SCHEDULED")
        minutos_desde_inicio = -minutos_restantes if minutos_restantes < 0 else 0
        es_finalizado = estado_api in ["FINISHED", "FINALIZADO", "AWARDED"]
        
        es_en_juego = False
        if not es_finalizado:
            if estado_api in ["IN_PLAY", "PAUSED", "HT", "LIVE"]:
                es_en_juego = True
            elif 0 <= minutos_desde_inicio <= 135 and estado_api not in ["CANCELLED", "POSTPONED", "TIMED", "SUSPENDED"]:
                es_en_juego = True

        if es_en_juego and (goles_local is None or goles_visitante is None):
            goles_local = 0
            goles_visitante = 0

        marcador_str = None
        if goles_local is not None and goles_visitante is not None:
            marcador_str = f"{goles_local} - {goles_visitante}"

        estado_normalizado = estado_api
        minuto_en_juego_str = None

        if es_finalizado:
            estado_normalizado = "FINISHED"
        elif estado_api in ["PAUSED", "HT"] or (45 <= minutos_desde_inicio <= 65 and es_en_juego):
            estado_normalizado = "HT"
            minuto_en_juego_str = "Descanso"
        elif es_en_juego:
            estado_normalizado = "IN_PLAY"
            if minutos_desde_inicio <= 45:
                minuto_en_juego_str = f"{max(1, minutos_desde_inicio)}'"
            elif minutos_desde_inicio <= 65:
                minuto_en_juego_str = "Descanso"
            elif minutos_desde_inicio <= 110:
                m2t = min(90, max(46, minutos_desde_inicio - 15))
                minuto_en_juego_str = f"{m2t}'"
            else:
                minuto_en_juego_str = "90+'"
        elif estado_api in ["TIMED", "SCHEDULED"] and minutos_desde_inicio > 150:
            # La API sigue diciendo "programado" aunque el partido ya debería haber terminado:
            # no se da por finalizado (no hay marcador) hasta que la API publique el resultado.
            estado_normalizado = "PENDING_RESULT"
            minuto_en_juego_str = "Esperando resultado"

        info_partido_actual = {
            "id": p.get("id"),
            "partido": partido_nombre,
            "local": nombre_local,
            "visitante": nombre_visitante,
            "estado": estado_normalizado,
            "estado_original": estado_api,
            "minuto_juego": minuto_en_juego_str,
            "goles_local": goles_local,
            "goles_visitante": goles_visitante,
            "marcador": marcador_str,
            "fecha": fecha_madrid_partido,
            "hora": hora_madrid_partido,
            "fecha_hora_display": fecha_hora_display,
            "escudo_local": escudo_local,
            "escudo_visitante": escudo_visitante
        }

        partidos_map_por_id[str(p.get("id"))] = info_partido_actual
        partidos_map_por_nombres[partido_nombre] = info_partido_actual
        key_norm = f"{normalizar_texto(nombre_local)} vs {normalizar_texto(nombre_visitante)}"
        partidos_map_por_nombres[key_norm] = info_partido_actual

        form_info = calcular_factor_racha_real(p.get("id", 0), nombre_local, nombre_visitante, historial_equipos)
        prev = partidos_previos_map.get(str(p.get("id")))
        analizado = bool(prev and prev.get("analizado"))
        nota_cuotas = prev.get("nota_cuotas") if prev else None
        analisis = None
        analisis_nuevo = False

        if analizado:
            analisis = reconstruir_analisis(prev, form_info)
        elif (not es_finalizado) and (not es_en_juego) and VENTANA_MIN <= minutos_restantes <= VENTANA_MAX:
            inicio_dt = datetime.fromtimestamp(timestamp_inicio_ms / 1000.0, timezone.utc) if timestamp_inicio_ms else None
            analisis, definitivo, nota = analizar_partido_con_cuotas(comp_code, nombre_local, nombre_visitante, inicio_dt, form_info, cache_eventos_odds)
            nota_cuotas = nota
            if definitivo:
                analizado = True
                analisis_nuevo = analisis is not None
            else:
                analisis = None

        acertado_partido = None
        id_alerta_unica = None
        ya_registrada = False
        if analisis:
            if es_finalizado and goles_local is not None and goles_visitante is not None:
                acertado_partido = verificar_acierto(
                    analisis["mercado"],
                    analisis["tipo_mercado"],
                    goles_local,
                    goles_visitante,
                    nombre_local=nombre_local,
                    nombre_visitante=nombre_visitante,
                    equipo_pronosticado=analisis.get("equipo_pronosticado")
                )
            id_alerta_unica = f"{p.get('id')}_{analisis['tipo_mercado']}"
            ya_registrada = any(a.get("id_alerta") == id_alerta_unica or (a.get("partido") == partido_nombre and a.get("tipo_mercado") == analisis["tipo_mercado"]) for a in alertas_acumuladas)

        fue_enviado_telegram = False

        # ALERTA OFICIAL: mejor cuota real entre las casas objetivo con +EV >= 3% frente al consenso (T-90m a T-15m)
        if analisis_nuevo and analisis["ev"] >= EV_MINIMO_PCT and not ya_registrada:
            fue_enviado_telegram = True
            alerta_msg = (
                f"🎯 <b>ALERTA CUANTITATIVA (+EV) — [PRE-PARTIDO]</b>\n\n"
                f"🏆 <b>Competición:</b> {comp_info['name']}\n"
                f"⚽ <b>Partido:</b> {partido_nombre}\n"
                f"⏰ <b>Inicio:</b> {fecha_hora_display} (en {minutos_restantes} min)\n"
                f"{analisis.get('icono_tg', '🛡️')} <b>Mercado:</b> {analisis['mercado']}\n"
                f"💰 <b>Cuota {analisis.get('casa', '')}:</b> @{analisis['cuota']}\n"
                f"📈 <b>Ventaja (+EV vs consenso):</b> +{analisis['ev']}%\n"
                f"💡 <b>Stake Sugerido:</b> {analisis['stake']}/10 unidades\n"
                f"🧮 <b>Prob. de consenso ({analisis.get('n_casas', '?')} casas):</b> {analisis['prob_modelo']}\n"
                f"📊 <b>Filtro de Racha:</b> {analisis['form_info']['resumen']}\n"
                f"📈 <b>Dinámica:</b> {analisis['form_info']['tendencia']}\n\n"
                f"⚡ <i>Apex Quant Engine • Cuotas reales de mercado</i>"
            )
            enviar_telegram(alerta_msg, url_accion=APP_URL, texto_boton="📱 Abrir en Web App")
            alertas_acumuladas.append({
                "id_partido": str(p.get("id")),
                "id_alerta": id_alerta_unica,
                "partido": partido_nombre,
                "local": nombre_local,
                "visitante": nombre_visitante,
                "escudo_local": escudo_local,
                "escudo_visitante": escudo_visitante,
                "mercado": analisis["mercado"],
                "tipo_mercado": analisis["tipo_mercado"],
                "categoria_visual": analisis.get("categoria_visual", "doble_oportunidad"),
                "equipo_pronosticado": analisis.get("equipo_pronosticado"),
                "casa": analisis.get("casa"),
                "cuota": f"@{analisis['cuota']}",
                "ev": f"+{analisis['ev']}%",
                "stake": f"{analisis['stake']}/10",
                "hora": hora_madrid_partido,
                "fecha": fecha_madrid_partido,
                "fecha_hora_display": fecha_hora_display,
                "semana_id": semana_actual_id,
                "es_ht": False,
                "es_semana_actual": True,
                "estado_partido": estado_normalizado,
                "marcador": marcador_str,
                "marcador_final": None,
                "finalizado": False,
                "acertado": None,
                "liquidada_telegram": False
            })

        tiene_pron = analisis is not None
        item = {
            "id": p.get("id"),
            "local": nombre_local,
            "visitante": nombre_visitante,
            "escudo_local": escudo_local,
            "escudo_visitante": escudo_visitante,
            "liga": comp_info["name"],
            "liga_key": comp_info["key"],
            "fecha": fecha_madrid_partido,
            "hora": hora_madrid_partido,
            "fecha_hora_display": fecha_hora_display,
            "hora_utc": hora_utc_raw,
            "utcDate": hora_utc_raw,
            "timestamp_ms": timestamp_inicio_ms,
            "minutos_restantes": minutos_restantes,
            "estado": estado_normalizado,
            "minuto_juego": minuto_en_juego_str,
            "marcador": marcador_str,
            "goles_local": goles_local,
            "goles_visitante": goles_visitante,
            "mercado": analisis["mercado"] if tiene_pron else None,
            "tipo_mercado": analisis["tipo_mercado"] if tiene_pron else None,
            "categoria_visual": analisis.get("categoria_visual") if tiene_pron else None,
            "equipo_pronosticado": analisis.get("equipo_pronosticado") if tiene_pron else None,
            "cuota": analisis["cuota"] if tiene_pron else None,
            "prob_modelo": analisis["prob_modelo"] if tiene_pron else None,
            "ev": f"+{analisis['ev']}%" if tiene_pron else None,
            "ev_numero": analisis["ev"] if tiene_pron else None,
            "stake": analisis["stake"] if tiene_pron else None,
            "n_casas": analisis.get("n_casas") if tiene_pron else None,
            "casa": analisis.get("casa") if tiene_pron else None,
            "tiene_pronostico": tiene_pron,
            "analizado": analizado,
            "nota_cuotas": nota_cuotas,
            "semana_id": semana_actual_id,
            "telegram_enviado": bool(fue_enviado_telegram or ya_registrada or (prev and prev.get("telegram_enviado"))),
            "es_empate_ht": False,
            "acertado": acertado_partido,
            "form_info": form_info
        }
        partidos_para_web.append(item)

    # RECONCILIACIÓN Y LIQUIDACIÓN
    for alerta in alertas_acumuladas:
        p_id = str(alerta.get("id_partido", ""))
        p_nombre = alerta.get("partido", "")
        p_norm = normalizar_texto(p_nombre)

        partido_encontrado = None
        if p_id and p_id in partidos_map_por_id:
            partido_encontrado = partidos_map_por_id[p_id]
        elif p_nombre in partidos_map_por_nombres:
            partido_encontrado = partidos_map_por_nombres[p_nombre]
        else:
            for k, info in partidos_map_por_nombres.items():
                if normalizar_texto(k) == p_norm or (info["local"] in p_nombre and info["visitante"] in p_nombre):
                    partido_encontrado = info
                    break

        if partido_encontrado:
            alerta["estado_partido"] = partido_encontrado["estado"]
            if partido_encontrado["marcador"]:
                alerta["marcador"] = partido_encontrado["marcador"]

            if partido_encontrado["estado"] == "FINISHED":
                g_loc = partido_encontrado["goles_local"]
                g_vis = partido_encontrado["goles_visitante"]
                marcador_fin = partido_encontrado["marcador"] or (f"{g_loc} - {g_vis}" if g_loc is not None else None)
                
                alerta["finalizado"] = True
                alerta["marcador_final"] = marcador_fin
                alerta["goles_local"] = g_loc
                alerta["goles_visitante"] = g_vis

                acertado = verificar_acierto(
                    alerta["mercado"],
                    alerta.get("tipo_mercado", ""),
                    g_loc,
                    g_vis,
                    nombre_local=partido_encontrado["local"],
                    nombre_visitante=partido_encontrado["visitante"],
                    equipo_pronosticado=alerta.get("equipo_pronosticado")
                )
                alerta["acertado"] = acertado

                if not alerta.get("liquidada_telegram"):
                    nombre_partido_display = p_nombre or f"{partido_encontrado['local']} vs {partido_encontrado['visitante']}"
                    if acertado:
                        msg_settle = (
                            f"⚽ <b>{nombre_partido_display}</b>\n"
                            f"📌 <b>Pronóstico:</b> {alerta['mercado']}\n"
                            f"✅ <b>Resultado:</b> ACERTADO\n"
                            f"🏁 <b>Marcador Final:</b> {marcador_fin or 'Final'}\n"
                            f"💰 <b>Cuota Cobrada:</b> {alerta['cuota']}\n"
                            f"💡 <b>Stake:</b> {alerta['stake']}\n\n"
                            f"🎉 <i>¡Verificado y sumado a la Efectividad Oficial en la App!</i>\n"
                            f"⚡ <i>Apex Quant Engine</i>"
                        )
                    else:
                        msg_settle = (
                            f"⚽ <b>{nombre_partido_display}</b>\n"
                            f"📌 <b>Pronóstico:</b> {alerta['mercado']}\n"
                            f"❌ <b>Resultado:</b> PERDIDO\n"
                            f"🏁 <b>Resultado Final:</b> {marcador_fin or 'Final'}\n"
                            f"💡 <b>Stake:</b> {alerta['stake']} (Control estricto de banca)\n\n"
                            f"⚡ <i>Apex Quant Engine • Disciplina a Largo Plazo</i>"
                        )
                    enviar_telegram(msg_settle, url_accion=APP_URL, texto_boton="📱 Ver en la Web App")
                    alerta["liquidada_telegram"] = True

    # RESUMEN DOMINICAL
    if dia_semana == 6 and hora_int >= 22 and resumen_semanal_enviado != semana_actual_id:
        partidos_domingo = [p for p in partidos_para_web if p["fecha"] == hoy_madrid_str]
        partidos_pendientes_domingo = [p for p in partidos_domingo if p["estado"] != "FINISHED"]
        
        if len(partidos_pendientes_domingo) == 0 or (hora_int == 23 and ahora_madrid.minute >= 45):
            alertas_semana_actual = [a for a in alertas_acumuladas if a.get("semana_id") == semana_actual_id and a.get("finalizado")]
            resumen_fin = calcular_resumen_financiero(alertas_semana_actual)
            total_semana = resumen_fin["finalizadas"]
            
            if total_semana > 0:
                aciertos_semana = resumen_fin["acertadas"]
                fallos_semana = resumen_fin["falladas"]
                pct_acierto = round((aciertos_semana / total_semana) * 100, 1)
                signo_u = "+" if resumen_fin["unidades_netas"] >= 0 else ""

                msg_resumen_domingo = (
                    f"📊 <b>CIERRE SEMANAL OFICIAL — APEX QUANT ANALYTICS</b> 🏆\n\n"
                    f"📅 <b>Semana:</b> {semana_actual_id} (Finalizada)\n"
                    f"📈 <b>Total Pronósticos Oficiales:</b> <b>{total_semana}</b>\n\n"
                    f"✅ <b>Alertas Acertadas:</b> <b>{aciertos_semana}</b> ({pct_acierto}%)\n"
                    f"❌ <b>Alertas Falladas:</b> <b>{fallos_semana}</b>\n"
                    f"🎯 <b>Efectividad Oficial:</b> <b>{pct_acierto}%</b>\n\n"
                    f"💰 <b>Rendimiento Neto:</b> <b>{signo_u}{resumen_fin['unidades_netas']} Unidades</b>\n"
                    f"📈 <b>Yield / ROI Semanal:</b> <b>{signo_u}{resumen_fin['roi_pct']}%</b>\n\n"
                    f"🔄 <i>Las estadísticas y partidos se reiniciarán automáticamente a las 00:00 del lunes para la nueva semana.</i>\n"
                    f"⚡ <i>Apex Quant Engine • Máxima Transparencia y Disciplina</i>"
                )
                enviar_telegram(msg_resumen_domingo, url_accion=APP_URL, texto_boton="📱 Abrir Balance Completo en la App")
                resumen_semanal_enviado = semana_actual_id

    # RESUMEN MENSUAL
    dia_manana_madrid = ahora_madrid + timedelta(days=1)
    es_ultimo_dia_mes = (dia_manana_madrid.month != ahora_madrid.month)

    if es_ultimo_dia_mes and hora_int >= 22 and resumen_mensual_enviado != mes_actual_id:
        partidos_hoy_mes = [p for p in partidos_para_web if p["fecha"] == hoy_madrid_str]
        partidos_pendientes_mes = [p for p in partidos_hoy_mes if p["estado"] != "FINISHED"]

        if len(partidos_pendientes_mes) == 0 or (hora_int == 23 and ahora_madrid.minute >= 45):
            alertas_mes_totales = []
            archivo_hist = "historico_mensual.json"
            if os.path.exists(archivo_hist):
                try:
                    with open(archivo_hist, "r", encoding="utf-8") as f:
                        hist_data = json.load(f)
                        alertas_mes_totales.extend(hist_data.get(mes_actual_id, []))
                except Exception as e:
                    pass

            ids_ya_contadas = {a.get("id_alerta") for a in alertas_mes_totales}
            for a in alertas_acumuladas:
                f_a = a.get("fecha", "")
                if f_a.startswith(mes_actual_id) and a.get("finalizado") and a.get("id_alerta") not in ids_ya_contadas:
                    alertas_mes_totales.append(a)
                    ids_ya_contadas.add(a.get("id_alerta"))

            resumen_mes_fin = calcular_resumen_financiero(alertas_mes_totales)
            total_mes = resumen_mes_fin["finalizadas"]

            if total_mes > 0:
                aciertos_mes = resumen_mes_fin["acertadas"]
                fallos_mes = resumen_mes_fin["falladas"]
                pct_acierto_mes = round((aciertos_mes / total_mes) * 100, 1)
                signo_u_mes = "+" if resumen_mes_fin["unidades_netas"] >= 0 else ""
                signo_roi_mes = "+" if resumen_mes_fin["roi_pct"] >= 0 else ""

                semanas_map = {}
                for a in alertas_mes_totales:
                    sem_key = a.get("semana_id") or "S/D"
                    if sem_key not in semanas_map:
                        semanas_map[sem_key] = []
                    semanas_map[sem_key].append(a)

                lineas_semanas = []
                for idx_sem, (sem_k, sem_alertas) in enumerate(sorted(semanas_map.items()), 1):
                    res_sem = calcular_resumen_financiero(sem_alertas)
                    signo_sem_u = "+" if res_sem["unidades_netas"] >= 0 else ""
                    signo_sem_roi = "+" if res_sem["roi_pct"] >= 0 else ""
                    lineas_semanas.append(
                        f"▫️ <b>Semana {idx_sem} ({sem_k}):</b> {signo_sem_u}{res_sem['unidades_netas']} U. (ROI {signo_sem_roi}{res_sem['roi_pct']}%)"
                    )

                bloque_semanas_str = "\n".join(lineas_semanas) if lineas_semanas else "▫️ Registro semanal consolidado"
                nombres_meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
                nombre_mes_str = nombres_meses[ahora_madrid.month - 1]
                año_str = ahora_madrid.strftime('%Y')

                msg_resumen_mensual = (
                    f"🏆 <b>CIERRE MENSUAL OFICIAL — APEX QUANT ANALYTICS</b> 📊\n\n"
                    f"📅 <b>Mes:</b> <b>{nombre_mes_str} {año_str}</b> (Finalizado)\n"
                    f"📈 <b>Total Pronósticos Oficiales:</b> <b>{total_mes}</b>\n\n"
                    f"✅ <b>Alertas Acertadas:</b> <b>{aciertos_mes}</b> ({pct_acierto_mes}%)\n"
                    f"❌ <b>Alertas Falladas:</b> <b>{fallos_mes}</b>\n"
                    f"🎯 <b>Efectividad Mensual:</b> <b>{pct_acierto_mes}%</b>\n\n"
                    f"💰 <b>Rendimiento Neto:</b> <b>{signo_u_mes}{resumen_mes_fin['unidades_netas']} Unidades</b>\n"
                    f"📈 <b>Yield / ROI Mensual:</b> <b>{signo_roi_mes}{resumen_mes_fin['roi_pct']}%</b>\n\n"
                    f"📊 <b>EVOLUCIÓN SEMANA A SEMANA:</b>\n"
                    f"{bloque_semanas_str}\n\n"
                    f"⚡ <i>Apex Quant Engine • Transparencia, Disciplina y Consistencia</i>"
                )
                enviar_telegram(msg_resumen_mensual, url_accion=APP_URL, texto_boton="📱 Abrir Balance Completo en la App")
                resumen_mensual_enviado = mes_actual_id

    alertas_semana_act = [a for a in alertas_acumuladas if a.get("semana_id") == semana_actual_id]
    metricas_semana = calcular_resumen_financiero(alertas_semana_act)

    # FUSIÓN DE PARTIDOS
    partidos_guardar = list(partidos_para_web)
    ids_guardados = {p["id"] for p in partidos_guardar}

    for prev_p in partidos_previos:
        p_id = prev_p.get("id")
        p_fecha = prev_p.get("fecha", "")
        if p_id not in ids_guardados:
            if p_fecha >= lunes_semana_str:
                partidos_guardar.append(prev_p)
                ids_guardados.add(p_id)

    datos_completos = {
        "ultima_actualizacion": hora_madrid_str,
        "huso_horario": "Europe/Madrid",
        "semana_activa": semana_guardada,
        "lunes_semana": lunes_semana_str,
        "domingo_semana": domingo_semana_str,
        "resumen_semanal_enviado_para": resumen_semanal_enviado,
        "resumen_mensual_enviado_para": resumen_mensual_enviado,
        "metricas_semana": metricas_semana,
        "total_partidos_hoy": len(partidos_guardar),
        "partidos": partidos_guardar,
        "creditos_odds_restantes": ODDS_ESTADO["restantes"],
        "api_cuotas_estado": estado_api_cuotas,
        "alertas": alertas_acumuladas[-70:]
    }

    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump(datos_completos, f, ensure_ascii=False, indent=2)

    total_fin = sum(1 for p in partidos_guardar if p.get("estado") == "FINISHED")
    print(f"💳 The Odds API: {ODDS_ESTADO['consultas']} consultas de cuotas en este ciclo | créditos restantes: {ODDS_ESTADO['restantes']}")
    print(f"📁 datos.json guardado. Partidos semana: {len(partidos_guardar)} (Finalizados: {total_fin}) | Alertas: {len(alertas_acumuladas)} | Semana: {semana_guardada}")

if __name__ == "__main__":
    ejecutar_ciclo()
