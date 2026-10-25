import os
import json
import hashlib
import requests
import time
import unicodedata
import math
import itertools
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

# ==============================================================================
# CUOTAS REALES (THE ODDS API) - WINAMAX vs CONSENSO DEL MERCADO
# Solo se consultan cuotas (con coste de créditos) para partidos que empiezan
# entre 15 y 90 minutos. El calendario viene de football-data.org (gratis) y la
# lista de eventos de The Odds API (/events) tampoco consume créditos.
# ==============================================================================
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_SPORT_KEYS = {
    "PD": "soccer_spain_la_liga",
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
MIN_CASAS_CONSENSO = int(os.getenv("ODDS_MIN_CASAS", "4"))
CREDITOS_RESERVA = float(os.getenv("ODDS_MIN_CREDITS", "20"))
MAX_CONSULTAS_CICLO = int(os.getenv("ODDS_MAX_CALLS", "10"))
EV_MINIMO_PCT = float(os.getenv("EV_MINIMO_PCT", "3.0"))     # filtro de alerta (+EV >= 3% por defecto)
CUOTA_MAXIMA = float(os.getenv("ODDS_MAX_CUOTA", "3.0"))   # sin alertas a cuotas "locas" (resultados muy improbables)
PROB_MINIMA = float(os.getenv("ODDS_MIN_PROB", "0.40"))    # probabilidad mínima para alertar (nada de apuestas "a la lotería")

# Combinadas de favoritos (máximo 3 partidos, todas las selecciones en la misma casa)
COMBI_ACTIVA = os.getenv("COMBI_ACTIVA", "1") == "1"
COMBI_MAX_PATAS = 3
COMBI_EV_PATA_MIN = float(os.getenv("COMBI_EV_PATA_MIN", "1.0"))       # cada selección debe tener al menos +1% de ventaja
COMBI_PROB_PATA_MIN = float(os.getenv("COMBI_PROB_PATA_MIN", "0.50"))  # y ser claramente favorita
COMBI_CUOTA_PATA = (1.25, 2.30)
COMBI_PROB_MIN = float(os.getenv("COMBI_PROB_MIN", "0.30"))            # probabilidad conjunta mínima
COMBI_EV_MIN = float(os.getenv("COMBI_EV_MIN", "6.0"))                 # ventaja conjunta mínima (%)
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


# ---------------------------------------------------------------------------
# Perfiles de mercados (cada mercado consultado cuesta 1 crédito por región y partido)
# ---------------------------------------------------------------------------
PERFILES_MERCADOS = {
    "reducido": "h2h,totals,alternate_totals,btts,double_chance",   # 1X2 + doble oportunidad + goles (1.5/2.5/3.5) + ambos marcan = 5 créditos/partido
    "basico": "h2h,totals,btts,double_chance",
    "medio": "h2h,totals,btts,double_chance,h2h_h1,totals_h1,alternate_totals,team_totals,spreads",
    "completo": ("h2h,h2h_h1,double_chance,double_chance_h1,totals,totals_h1,alternate_totals,alternate_totals_h1,"
                 "team_totals,alternate_team_totals,btts,spreads,alternate_spreads,alternate_totals_corners,alternate_totals_cards"),
}
ODDS_PERFIL = os.getenv("ODDS_PERFIL", "reducido")      # reducido | auto | basico | medio | completo
# Familias de mercado que se analizan (el resto se ignora aunque la casa los ofrezca)
MERCADOS_ACTIVOS = {m.strip().upper() for m in os.getenv("MERCADOS_ACTIVOS", "1X2,DC,TOT,BTTS").split(",") if m.strip()}
ESCALAS_ACTIVAS = {m.strip().upper() for m in os.getenv("ESCALAS_ACTIVAS", "FT").split(",") if m.strip()}
ODDS_MARKETS_FORZADOS = os.getenv("ODDS_MARKETS", "")   # si se define, sustituye al perfil


def mercados_a_consultar():
    if ODDS_MARKETS_FORZADOS:
        return ODDS_MARKETS_FORZADOS
    perfil = ODDS_PERFIL
    ODDS_ESTADO["perfil"] = perfil
    if perfil == "auto":
        r = ODDS_ESTADO["restantes"]
        perfil = "basico" if r is None else ("completo" if r >= 4000 else ("medio" if r >= 1500 else "basico"))
    ODDS_ESTADO["perfil"] = perfil
    return PERFILES_MERCADOS.get(perfil, PERFILES_MERCADOS["basico"])


def consultar_cuotas_evento(sport_key, event_id):
    base = mercados_a_consultar()
    orden = ["completo", "medio", "basico"]
    intentos = [base]
    perfil = ODDS_ESTADO.get("perfil") or ODDS_PERFIL
    if not ODDS_MARKETS_FORZADOS and perfil in orden:
        intentos += [PERFILES_MERCADOS[k] for k in orden[orden.index(perfil) + 1:]]
    intentos += ["h2h,totals,btts,double_chance", "h2h,totals,btts", "h2h,totals"]
    vistos, ODDS_ESTADO["consultas"] = [], ODDS_ESTADO["consultas"] + 1
    for mk in intentos:
        if mk in vistos:
            continue
        vistos.append(mk)
        params = {"regions": ODDS_REGIONS, "markets": mk, "oddsFormat": "decimal", "dateFormat": "iso"}
        data, status = odds_get(f"/sports/{sport_key}/events/{event_id}/odds", params)
        if data:
            return data
        if status != 422:
            break
        print(f"   Aviso: la API rechazó algún mercado de «{mk}» (422); se prueba un perfil más pequeño")
    return None


def _lado_equipo(descr, home, away):
    d = (descr or "").strip()
    if not d:
        return None
    if equipos_equivalentes(d, home):
        return "L"
    if equipos_equivalentes(d, away):
        return "V"
    return None


def parsear_bookmaker(bk, ev):
    """Convierte los mercados de una casa en grupos {clave_grupo: {seleccion: cuota}}.
    Claves: ("1X2", esc) ("DC", esc) ("TOT", esc, linea) ("TT", "FT", L|V, linea) ("BTTS", "FT")
            ("HC", "FT", linea_del_local) ("COR", "FT", linea) ("CARD", "FT", linea)   esc = FT | H1"""
    home, away = ev.get("home_team") or "", ev.get("away_team") or ""
    hl, al = home.lower(), away.lower()
    g = {}

    def put(gk, sel, precio):
        g.setdefault(gk, {}).setdefault(sel, precio)

    for m in bk.get("markets", []):
        key = m.get("key") or ""
        esc = "H1" if key.endswith("_h1") else "FT"
        for o in m.get("outcomes", []):
            precio = o.get("price")
            if not precio or precio <= 1.0:
                continue
            low = (o.get("name") or "").strip().lower()
            punto = o.get("point")
            lado_ou = "O" if low == "over" else ("U" if low == "under" else None)
            if key in ("h2h", "h2h_3_way", "h2h_h1", "h2h_3_way_h1"):
                if low == hl:
                    put(("1X2", esc), "1", precio)
                elif low == al:
                    put(("1X2", esc), "2", precio)
                elif low == "draw":
                    put(("1X2", esc), "X", precio)
            elif key in ("double_chance", "double_chance_h1"):
                if "draw" in low:
                    if hl and hl in low:
                        put(("DC", esc), "1X", precio)
                    elif al and al in low:
                        put(("DC", esc), "X2", precio)
                elif hl in low and al in low:
                    put(("DC", esc), "12", precio)
            elif key in ("totals", "alternate_totals", "totals_h1", "alternate_totals_h1"):
                if punto is not None and lado_ou:
                    put(("TOT", esc, float(punto)), lado_ou, precio)
            elif key in ("team_totals", "alternate_team_totals"):
                eq = _lado_equipo(o.get("description"), home, away)
                if eq and punto is not None and lado_ou:
                    put(("TT", "FT", eq, float(punto)), lado_ou, precio)
            elif key == "btts":
                if low == "yes":
                    put(("BTTS", "FT"), "SI", precio)
                elif low == "no":
                    put(("BTTS", "FT"), "NO", precio)
            elif key in ("spreads", "alternate_spreads"):
                if punto is None:
                    continue
                if low == hl:
                    put(("HC", "FT", float(punto)), "H", precio)
                elif low == al:
                    put(("HC", "FT", -float(punto)), "A", precio)
            elif "totals" in key and "corners" in key and punto is not None and lado_ou:
                put(("COR", "FT", float(punto)), lado_ou, precio)
            elif "totals" in key and "cards" in key and punto is not None and lado_ou:
                put(("CARD", "FT", float(punto)), lado_ou, precio)
    return g


def _quitar_margen(precios):
    inv = {k: 1.0 / v for k, v in precios.items() if v and v > 1.0}
    if len(inv) != len(precios) or not inv:
        return None
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()} if s > 0 else None


def _consenso(otros, extractor, minimo=None):
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
    if n < (minimo or MIN_CASAS_CONSENSO) or peso_total <= 0:
        return None, n
    return {k: v / peso_total for k, v in acum.items()}, n


def ev_y_stake(cuota, prob, push=0.0):
    """EV por unidad apostada (con devolución si hay push) y stake Kelly 1/4 (1-10)."""
    ev = prob * cuota + push - 1.0
    if ev <= 0:
        return round(ev * 100, 1), 0
    b = cuota - 1.0
    q = max(0.0, 1.0 - prob - push)
    kelly = (b * prob - q) / b
    stake = min(10, max(1, round(max(0.0, kelly * 0.25) * 40)))
    return round(ev * 100, 1), stake


# ==============================================================================
# MODELO ESTADÍSTICO PROPIO (Poisson con corrección Dixon-Coles simplificada)
# Usa los resultados reales de la temporada en football-data.org (1 llamada por liga y ciclo).
# Una apuesta solo se confirma si el modelo, por sí solo, también ve valor a esa cuota.
# ==============================================================================
STATS_PESO_MERCADO = float(os.getenv("STATS_PESO_MERCADO", "0.65"))   # peso del consenso en la probabilidad final
STATS_OBLIGATORIAS = os.getenv("STATS_OBLIGATORIAS", "1") == "1"      # alerta solo con respaldo estadístico
STATS_MIN_PARTIDOS = int(os.getenv("STATS_MIN_PARTIDOS", "5"))        # partidos mínimos por equipo
STATS_PRIOR_PARTIDOS = 6.0                                            # "partidos virtuales" de regresión a la media
DC_RHO = -0.05


def construir_fuerzas(matches):
    equipos, gh, ga, n = {}, 0, 0, 0
    res = []   # (fecha UTC, id local, id visitante, goles local, goles visitante)
    for m in matches:
        ft = (m.get("score") or {}).get("fullTime") or {}
        h, a = ft.get("home"), ft.get("away")
        hid = (m.get("homeTeam") or {}).get("id")
        aid = (m.get("awayTeam") or {}).get("id")
        if h is None or a is None or hid is None or aid is None:
            continue
        gh += h
        ga += a
        n += 1
        res.append((m.get("utcDate") or "", hid, aid, h, a))
        for tid, gf, gc in ((hid, h, a), (aid, a, h)):
            e = equipos.setdefault(tid, {"gf": 0, "gc": 0, "n": 0})
            e["gf"] += gf
            e["gc"] += gc
            e["n"] += 1
    if n < 20:
        return {"valido": False, "equipos": equipos, "res": res, "mu_home": 1.4, "mu_away": 1.1, "mu": 1.25}
    return {"valido": True, "equipos": equipos, "res": res, "mu_home": gh / n, "mu_away": ga / n, "mu": (gh + ga) / (2.0 * n)}


def obtener_fuerzas_liga(comp_code, cache_stats):
    if comp_code in cache_stats:
        return cache_stats[comp_code]
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    url = f"https://api.football-data.org/v4/competitions/{comp_code}/matches?status=FINISHED"
    fuerzas = None
    for intento in range(2):
        try:
            res = fd_get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                fuerzas = construir_fuerzas(res.json().get("matches", []))
                break
            if res.status_code == 429:
                time.sleep(4)
                continue
            print(f"   Aviso estadísticas {comp_code}: HTTP {res.status_code}")
            break
        except Exception as e:
            print(f"   Aviso estadísticas {comp_code}: {e}")
            time.sleep(1.5)
    cache_stats[comp_code] = fuerzas
    time.sleep(1.0)
    return fuerzas


def _poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


STATS_H1_SHARE = float(os.getenv("STATS_H1_SHARE", "0.44"))   # parte de los goles esperados que cae en la 1ª mitad


def calcular_modelo_estadistico(comp_code, local_id, visitante_id, cache_stats):
    f = obtener_fuerzas_liga(comp_code, cache_stats)
    if not f or not f.get("valido") or local_id not in f["equipos"] or visitante_id not in f["equipos"]:
        return None
    el, ev_ = f["equipos"][local_id], f["equipos"][visitante_id]
    if el["n"] < STATS_MIN_PARTIDOS or ev_["n"] < STATS_MIN_PARTIDOS:
        return None
    mu, K = f["mu"], STATS_PRIOR_PARTIDOS

    def tasa(e, clave):
        return (e[clave] + K * mu) / (e["n"] + K)

    lam_h = f["mu_home"] * (tasa(el, "gf") / mu) * (tasa(ev_, "gc") / mu)
    lam_a = f["mu_away"] * (tasa(ev_, "gf") / mu) * (tasa(el, "gc") / mu)
    lam_h, lam_a = max(0.2, min(4.5, lam_h)), max(0.2, min(4.5, lam_a))

    N = 10
    mat = [[_poisson(i, lam_h) * _poisson(j, lam_a) for j in range(N)] for i in range(N)]
    mat[0][0] *= max(0.0, 1.0 - lam_h * lam_a * DC_RHO)
    mat[0][1] *= max(0.0, 1.0 + lam_h * DC_RHO)
    mat[1][0] *= max(0.0, 1.0 + lam_a * DC_RHO)
    mat[1][1] *= max(0.0, 1.0 - DC_RHO)
    tot = sum(sum(r) for r in mat)
    mat = [[v / tot for v in r] for r in mat]

    lh1, la1 = lam_h * STATS_H1_SHARE, lam_a * STATS_H1_SHARE
    N1 = 8
    mat1 = [[_poisson(i, lh1) * _poisson(j, la1) for j in range(N1)] for i in range(N1)]
    tot1 = sum(sum(r) for r in mat1)
    mat1 = [[v / tot1 for v in r] for r in mat1]

    return {"mat": mat, "mat1": mat1, "xg_local": round(lam_h, 2), "xg_visitante": round(lam_a, 2)}


# ==============================================================================
# SELECCIONES: especificación, probabilidad del modelo, texto y liquidación
# spec = {"t": tipo, "s": lado, "l": línea, "sc": "FT"|"H1", "team": "L"|"V"}
# ==============================================================================
def pred_win(spec):
    t, s, l = spec["t"], spec.get("s"), spec.get("l")
    if t == "1X2":
        return {"1": lambda i, j: i > j, "X": lambda i, j: i == j, "2": lambda i, j: i < j}[s]
    if t == "DC":
        return {"1X": lambda i, j: i >= j, "X2": lambda i, j: i <= j, "12": lambda i, j: i != j}[s]
    if t == "TOT":
        return (lambda i, j: i + j > l) if s == "O" else (lambda i, j: i + j < l)
    if t == "TT":
        if spec["team"] == "L":
            return (lambda i, j: i > l) if s == "O" else (lambda i, j: i < l)
        return (lambda i, j: j > l) if s == "O" else (lambda i, j: j < l)
    if t == "BTTS":
        return (lambda i, j: i >= 1 and j >= 1) if s == "SI" else (lambda i, j: not (i >= 1 and j >= 1))
    if t == "HC":
        if spec["team"] == "L":
            return lambda i, j: (i + l - j) > 0
        return lambda i, j: (j + l - i) > 0
    return lambda i, j: False


def pred_push(spec):
    if spec["t"] == "HC" and float(spec["l"]).is_integer():
        l = spec["l"]
        if spec["team"] == "L":
            return lambda i, j: (i + l - j) == 0
        return lambda i, j: (j + l - i) == 0
    return None


def prob_modelo_sel(modelo, spec):
    """(prob_ganar, prob_devolución) según el modelo, o (None, None) si no hay modelo para ese mercado."""
    if not modelo or spec["t"] in ("COR", "CARD", "MULTI"):
        return None, None
    M = modelo["mat1"] if spec.get("sc") == "H1" else modelo["mat"]
    n = len(M)
    pw, pp = pred_win(spec), pred_push(spec)
    win = sum(M[i][j] for i in range(n) for j in range(n) if pw(i, j))
    push = sum(M[i][j] for i in range(n) for j in range(n) if pp(i, j)) if pp else 0.0
    return win, push


def prob_conjunta_modelo(modelo, specs):
    M = modelo["mat"]
    n = len(M)
    preds = [pred_win(s) for s in specs]
    return sum(M[i][j] for i in range(n) for j in range(n) if all(p(i, j) for p in preds))


def describir_sel(spec, local, visitante):
    t, s, l = spec["t"], spec.get("s"), spec.get("l")
    pref = "1ª Mitad: " if spec.get("sc") == "H1" else ""
    if t == "1X2":
        nombre = f"Victoria {local}" if s == "1" else (f"Victoria {visitante}" if s == "2" else "Empate")
        return f"{pref}{nombre} (1X2)"
    if t == "DC":
        base = {"1X": f"1X ({local} o Empate)", "X2": f"X2 (Empate o {visitante})",
                "12": f"12 ({local} o {visitante} - Sin Empate)"}[s]
        return f"{pref}Doble Oportunidad: {base}"
    if t == "TOT":
        return (f"{pref}Más de {l:g} Goles (Over {l:g})" if s == "O" else f"{pref}Menos de {l:g} Goles (Under {l:g})")
    if t == "TT":
        eq = local if spec["team"] == "L" else visitante
        return (f"{eq}: Más de {l:g} Goles (Over {l:g} equipo)" if s == "O" else f"{eq}: Menos de {l:g} Goles (Under {l:g} equipo)")
    if t == "BTTS":
        return "Ambos Equipos Marcan (Sí)" if s == "SI" else "Ambos Equipos Marcan (No)"
    if t == "HC":
        eq = local if spec["team"] == "L" else visitante
        return f"Hándicap {eq} {l:+g}"
    if t == "COR":
        return f"{'Más' if s == 'O' else 'Menos'} de {l:g} Córners"
    if t == "CARD":
        return f"{'Más' if s == 'O' else 'Menos'} de {l:g} Tarjetas"
    if t == "MULTI":
        return " + ".join(describir_sel(x, local, visitante) for x in spec["legs"])
    return str(spec)


def tipo_y_categoria(spec):
    t, sc = spec["t"], spec.get("sc", "FT")
    suf = "_H1" if sc == "H1" else ""
    if t == "1X2":
        return "1X2" + suf, "1x2"
    if t == "DC":
        return f"DOUBLE_CHANCE_{spec['s']}{suf}", "doble_oportunidad"
    if t == "TOT":
        if sc == "FT" and spec["s"] == "O" and abs(spec["l"] - 1.5) < 1e-9:
            return "OVER_15", "over15"
        return "GOLES" + suf, "goles"
    if t == "TT":
        return "TEAM_TOTAL", "goles_equipo"
    if t == "BTTS":
        return "BTTS", "btts"
    if t == "HC":
        return "HANDICAP", "handicap"
    if t == "COR":
        return "CORNERS", "corners"
    if t == "CARD":
        return "TARJETAS", "tarjetas"
    return "COMBO_MERCADOS", "combo_mercados"


def equipo_de_sel(spec, local, visitante):
    t = spec["t"]
    if t == "1X2":
        return local if spec["s"] == "1" else (visitante if spec["s"] == "2" else None)
    if t == "DC":
        return local if spec["s"] == "1X" else (visitante if spec["s"] == "X2" else None)
    if t in ("TT", "HC"):
        return local if spec["team"] == "L" else visitante
    return None


def resolver_seleccion(spec, gl, gv, hl=None, hv=None):
    """True / False / 'PUSH' / None (None = no se puede liquidar todavía)."""
    t = spec["t"]
    if t in ("COR", "CARD"):
        return None
    if t == "MULTI":
        res = [resolver_seleccion(x, gl, gv, hl, hv) for x in spec["legs"]]
        if any(r is False for r in res):
            return False
        return True if all(r is True for r in res) else None
    if spec.get("sc") == "H1":
        gl, gv = hl, hv
    if gl is None or gv is None:
        return None
    if pred_win(spec)(gl, gv):
        return True
    pp = pred_push(spec)
    if pp and pp(gl, gv):
        return "PUSH"
    return False


def evaluar_pick(sel, mercado, tipo, gl, gv, hl=None, hv=None, nombre_local="", nombre_visitante="", equipo_pronosticado=None):
    if sel:
        return resolver_seleccion(sel, gl, gv, hl, hv)
    return verificar_acierto(mercado, tipo, gl, gv, nombre_local, nombre_visitante, equipo_pronosticado)


# ==============================================================================
# GENERACIÓN DE CANDIDATOS (todos los mercados disponibles)
# ==============================================================================
LINEAS_TOTALES = (1.5, 2.5, 3.5)
LINEAS_EQUIPO = (0.5, 1.5, 2.5)
LINEAS_HANDICAP = (1.5, 2.0, 2.5)
ESPERADOS_GRUPO = {"1X2": 3, "TOT": 2, "TT": 2, "BTTS": 2, "HC": 2, "COR": 2, "CARD": 2}
MIN_CASAS_NICHO = int(os.getenv("ODDS_MIN_CASAS_NICHO", "3"))
PERMITIR_CORNERS_TARJETAS = os.getenv("PERMITIR_CORNERS_TARJETAS", "0") == "1"   # no se pueden liquidar solos
EV_MINIMO_SIN_MODELO = float(os.getenv("EV_MINIMO_SIN_MODELO", "5.0"))
COMBO_MERC_ACTIVO = os.getenv("COMBO_MERCADOS_ACTIVO", "1") == "1"
COMBO_MERC_PROB_MIN = float(os.getenv("COMBO_MERCADOS_PROB_MIN", "0.35"))
COMBO_MERC_MARGEN = 1.05      # la cuota mínima exige un 5% de ventaja sobre la cuota justa del modelo
COMBO_MERC_HAIRCUT = 0.90     # recorte prudente a la cuota de referencia (producto de cuotas)


def evaluar_seleccion(cuota, p_mercado, p_mod, push=0.0):
    """Mezcla consenso y modelo. Devuelve (prob_final, confirmado_por_el_modelo)."""
    if p_mod is not None:
        return STATS_PESO_MERCADO * p_mercado + (1.0 - STATS_PESO_MERCADO) * p_mod, (p_mod * cuota + push) > 1.0
    return p_mercado, False


def _spec_desde_grupo(gk, sel):
    tg, sc = gk[0], gk[1]
    if tg not in MERCADOS_ACTIVOS or sc not in ESCALAS_ACTIVAS:
        return None
    if tg == "1X2":
        return {"t": "1X2", "s": sel, "sc": sc}
    if tg == "TOT":
        return {"t": "TOT", "s": sel, "l": gk[2], "sc": sc} if gk[2] in LINEAS_TOTALES else None
    if tg == "TT":
        return {"t": "TT", "team": gk[2], "s": sel, "l": gk[3], "sc": "FT"} if gk[3] in LINEAS_EQUIPO else None
    if tg == "BTTS":
        return {"t": "BTTS", "s": sel, "sc": "FT"}
    if tg == "HC":
        lh = gk[2]
        if abs(lh) not in LINEAS_HANDICAP:
            return None
        return {"t": "HC", "team": "L" if sel == "H" else "V", "l": lh if sel == "H" else -lh, "sc": "FT"}
    if tg in ("COR", "CARD") and PERMITIR_CORNERS_TARJETAS:
        return {"t": tg, "s": sel, "l": gk[2], "sc": "FT"}
    return None


def _familia(spec):
    if spec["t"] in ("1X2", "DC", "HC"):
        return "RES"
    if spec["t"] in ("TOT", "TT"):
        return "GOL"
    return "BTTS" if spec["t"] == "BTTS" else None


def generar_candidatos(ev_odds, local, visitante, modelo=None):
    books, titulos = {}, {}
    for bk in ev_odds.get("bookmakers", []):
        books[bk["key"]] = parsear_bookmaker(bk, ev_odds)
        titulos[bk["key"]] = bk.get("title") or bk["key"]
    print(f"   Casas disponibles en {local} vs {visitante}: {', '.join(sorted(books)) or 'ninguna'}")
    objetivos = [k for k in BOOKMAKERS_OBJETIVO if k in books]
    if not objetivos:
        return [], 0, "Ninguna casa objetivo ofrece cuotas de este partido", None, None

    mejores, patas_por_casa = {}, {}
    mejor_combo = None
    n_max = 0
    tipos_vistos = set()

    for tk in objetivos:
        obj, casa = books[tk], titulos[tk]
        grupo = tk.split("_")[0]
        otros = [(k, b) for k, b in books.items() if k.split("_")[0] != grupo]
        cache = {}

        def cons_grupo(gk):
            if gk not in cache:
                esperado = ESPERADOS_GRUPO[gk[0]]
                minimo = MIN_CASAS_CONSENSO if (gk[1] == "FT" and gk[0] in ("1X2", "TOT", "BTTS")) else MIN_CASAS_NICHO
                cache[gk] = _consenso(otros, lambda b, g=gk, e=esperado: b.get(g) if len(b.get(g, {})) == e else None, minimo)
            return cache[gk]

        selecciones = []   # (spec, cuota, p_mercado, n)
        for gk, precios in obj.items():
            tipos_vistos.add(gk[0] + ("_H1" if gk[1] == "H1" else ""))
            if gk[0] == "DC":
                if "DC" not in MERCADOS_ACTIVOS or gk[1] not in ESCALAS_ACTIVAS:
                    continue
                c1, n1 = cons_grupo(("1X2", gk[1]))
                if not c1:
                    continue
                sumas = {"1X": c1["1"] + c1["X"], "X2": c1["X"] + c1["2"], "12": c1["1"] + c1["2"]}
                for sel, cuota in precios.items():
                    selecciones.append(({"t": "DC", "s": sel, "sc": gk[1]}, cuota, sumas[sel], n1))
                continue
            cons, n = cons_grupo(gk)
            if not cons:
                continue
            for sel, cuota in precios.items():
                spec = _spec_desde_grupo(gk, sel)
                if spec and sel in cons:
                    selecciones.append((spec, cuota, cons[sel], n))
        # el 1X2 siempre se evalúa aunque la casa no ofrezca doble oportunidad propia
        pool_combo, cands_casa = [], []
        for spec, cuota, p_merc, n in selecciones:
            n_max = max(n_max, n)
            p_mod, pp = prob_modelo_sel(modelo, spec)
            push = 0.0
            if spec["t"] == "HC" and float(spec["l"]).is_integer():
                if p_mod is None:
                    continue
                push = pp
                p_merc = p_merc * (1.0 - push)
            prob, conf = evaluar_seleccion(cuota, p_merc, p_mod, push)
            ev, stake = ev_y_stake(cuota, prob, push)
            if modelo and spec.get("sc", "FT") == "FT" and push == 0.0 and _familia(spec) and not (spec["t"] == "1X2" and spec["s"] == "X"):
                pool_combo.append({"spec": spec, "cuota": cuota, "prob": prob, "p_mod": p_mod, "ev_leg": prob * cuota - 1.0})
            sin_modelo = spec["t"] in ("COR", "CARD")
            if ev <= 0 or ev > EV_MAXIMO_PCT or cuota > CUOTA_MAXIMA or prob < PROB_MINIMA:
                continue
            if sin_modelo and ev < EV_MINIMO_SIN_MODELO:
                continue
            tipo, cat = tipo_y_categoria(spec)
            texto = describir_sel(spec, local, visitante)
            cand = {"mercado": texto, "tipo_mercado": tipo, "categoria_visual": cat, "sel": spec,
                    "equipo_pronosticado": equipo_de_sel(spec, local, visitante), "cuota": round(cuota, 2),
                    "prob_modelo": f"{round(prob * 100, 1)}%", "ev": ev, "stake": stake,
                    "prob_mercado": round(p_merc * 100, 1),
                    "prob_estadistica": round(p_mod * 100, 1) if p_mod is not None else None,
                    "confirmado_stats": bool(conf), "sin_modelo_ok": bool(sin_modelo),
                    "xg_local": modelo["xg_local"] if modelo else None,
                    "xg_visitante": modelo["xg_visitante"] if modelo else None,
                    "icono_tg": "⚽", "n_casas": n, "casa": casa,
                    "prob_final": round(prob, 4), "score": round(ev * math.sqrt(prob), 3)}
            cands_casa.append(cand)
            previo = mejores.get(texto)
            if previo is None or (cand["confirmado_stats"], cand["ev"]) > (previo["confirmado_stats"], previo["ev"]):
                mejores[texto] = cand

        # patas válidas para las combinadas de partidos (máx. 2 por casa)
        legs = [c for c in cands_casa
                if c["confirmado_stats"] and c["prob_final"] >= COMBI_PROB_PATA_MIN
                and COMBI_CUOTA_PATA[0] <= c["cuota"] <= COMBI_CUOTA_PATA[1] and c["ev"] >= COMBI_EV_PATA_MIN
                and not (c["sel"]["t"] == "HC" and float(c["sel"]["l"]).is_integer())]
        legs = sorted(legs, key=lambda c: c["score"], reverse=True)[:2]
        if legs:
            patas_por_casa[casa] = [{"mercado": c["mercado"], "tipo": c["tipo_mercado"], "sel": c["sel"],
                                     "equipo": c["equipo_pronosticado"], "cuota": c["cuota"], "prob": c["prob_final"],
                                     "ev": c["ev"], "confirmado": True} for c in legs]

        # combinado de mercados del mismo partido (máx. 3, una selección por familia)
        if COMBO_MERC_ACTIVO and modelo:
            por_fam = {}
            for it in pool_combo:
                if it["prob"] >= 0.50 and it["ev_leg"] >= 0.0 and it["p_mod"]:
                    por_fam.setdefault(_familia(it["spec"]), []).append(it)
            for fam in por_fam:
                por_fam[fam] = sorted(por_fam[fam], key=lambda x: x["prob"], reverse=True)[:3]
            fams = [f for f in ("RES", "GOL", "BTTS") if f in por_fam]
            for k in (2, 3):
                for combo_f in itertools.combinations(fams, k):
                    for elegidas in itertools.product(*[por_fam[f] for f in combo_f]):
                        specs = [e["spec"] for e in elegidas]
                        joint = prob_conjunta_modelo(modelo, specs)
                        ajuste = 1.0
                        for e in elegidas:
                            ajuste *= max(0.85, min(1.15, e["prob"] / e["p_mod"]))
                        p_joint = min(0.95, joint * ajuste)
                        if p_joint < COMBO_MERC_PROB_MIN:
                            continue
                        cuota_ref = math.prod(e["cuota"] for e in elegidas)
                        cuota_min = COMBO_MERC_MARGEN / p_joint
                        ev_est = (p_joint * cuota_ref * COMBO_MERC_HAIRCUT - 1.0) * 100.0
                        if cuota_ref * COMBO_MERC_HAIRCUT < cuota_min or ev_est > 60:
                            continue
                        score = ev_est * math.sqrt(p_joint)
                        if mejor_combo is None or score > mejor_combo["score"]:
                            spec_m = {"t": "MULTI", "legs": specs, "sc": "FT"}
                            mejor_combo = {"mercado": describir_sel(spec_m, local, visitante), "tipo_mercado": "COMBO_MERCADOS",
                                           "categoria_visual": "combo_mercados", "sel": spec_m, "equipo_pronosticado": None,
                                           "cuota": round(cuota_min, 2), "cuota_ref": round(cuota_ref, 2), "cuota_minima": True,
                                           "prob_modelo": f"{round(p_joint * 100, 1)}%",
                                           "ev": round((COMBO_MERC_MARGEN - 1.0) * 100, 1), "ev_estimado": round(ev_est, 1), "stake": 1,
                                           "prob_mercado": None, "prob_estadistica": round(joint * 100, 1),
                                           "confirmado_stats": True, "sin_modelo_ok": False,
                                           "xg_local": modelo["xg_local"], "xg_visitante": modelo["xg_visitante"],
                                           "icono_tg": "🧩", "n_casas": n_max, "casa": casa,
                                           "prob_final": round(p_joint, 4), "score": round(score, 3)}

    print(f"   Tipos de mercado recibidos: {', '.join(sorted(tipos_vistos)) or 'ninguno'}")
    fav = {"por_casa": patas_por_casa} if patas_por_casa else None
    cands = list(mejores.values())
    if not cands and not mejor_combo:
        if n_max < MIN_CASAS_CONSENSO:
            return [], n_max, f"Pocas casas para el consenso ({n_max}/{MIN_CASAS_CONSENSO})", fav, None
        return [], n_max, "Sin valor: ninguna casa supera al consenso del mercado", fav, None
    return cands, n_max, None, fav, mejor_combo


def es_alertable(c):
    if c.get("cuota_minima"):   # el combinado de mercados ya exige su propio margen mínimo
        return True
    return (c["ev"] >= EV_MINIMO_PCT and (c.get("confirmado_stats") or c.get("sin_modelo_ok") or not STATS_OBLIGATORIAS))


ODDS_DIA_RESET = int(os.getenv("ODDS_DIA_RESET", "1"))        # día del mes en que se renuevan los créditos
ODDS_FACTOR_PRESUPUESTO = float(os.getenv("ODDS_FACTOR_PRESUPUESTO", "1.25"))


def dias_hasta_reinicio(hoy):
    """Días (>= 1) que faltan para que se renueven los créditos de The Odds API."""
    reset = hoy.replace(day=min(ODDS_DIA_RESET, 28))
    if hoy.day >= reset.day:
        mes = hoy.month % 12 + 1
        anio = hoy.year + (1 if hoy.month == 12 else 0)
        reset = hoy.replace(year=anio, month=mes, day=min(ODDS_DIA_RESET, 28))
    return max(1, (reset - hoy).days)


def preparar_presupuesto(datos_previos, ahora_madrid):
    """Reparte los créditos que quedan entre los días que faltan para la renovación (lo no gastado un día se acumula)."""
    r = ODDS_ESTADO["restantes"]
    hoy_str = ahora_madrid.strftime("%Y-%m-%d")
    dia = dict(datos_previos.get("creditos_dia") or {})
    if r is None:
        ODDS_ESTADO["dia"], ODDS_ESTADO["presupuesto_dia"] = dia or None, None
        return
    if dia.get("fecha") != hoy_str or r > dia.get("restante_inicio", r):   # día nuevo o plan renovado
        dia = {"fecha": hoy_str, "restante_inicio": r}
    ODDS_ESTADO["dia"] = dia
    ODDS_ESTADO["presupuesto_dia"] = dia["restante_inicio"] / dias_hasta_reinicio(ahora_madrid.date() if hasattr(ahora_madrid, "date") else ahora_madrid)


def presupuesto_agotado():
    dia, pres, r = ODDS_ESTADO.get("dia"), ODDS_ESTADO.get("presupuesto_dia"), ODDS_ESTADO.get("restantes")
    if not dia or pres is None or r is None:
        return False
    gastado = dia["restante_inicio"] - r
    coste = len(mercados_a_consultar().split(","))
    return gastado > 0 and (gastado + coste) > pres * ODDS_FACTOR_PRESUPUESTO


def analizar_partido_con_cuotas(comp_code, local, visitante, inicio_utc, form_info, cache_eventos,
                                local_id=None, visitante_id=None, cache_stats=None):
    """Devuelve (analisis|None, definitivo, nota, fav). definitivo=False -> se reintenta en el siguiente ciclo.
    Se evalúan todos los mercados disponibles. Prioridad: 1) mejor pick individual alertable (valor + respaldo del
    modelo, ordenado por ventaja x raíz de la probabilidad); 2) combinado de mercados del mismo partido;
    3) mejor pick no alertable (grupo de control)."""
    sport_key = ODDS_SPORT_KEYS.get(comp_code)
    if not THE_ODDS_API_KEY or not sport_key:
        return None, False, "Sin API de cuotas configurada", None
    if ODDS_ESTADO["consultas"] >= MAX_CONSULTAS_CICLO:
        return None, False, "Límite de consultas por ciclo", None
    if ODDS_ESTADO["restantes"] is not None and ODDS_ESTADO["restantes"] <= CREDITOS_RESERVA:
        return None, False, "Créditos de The Odds API en reserva", None
    if presupuesto_agotado():
        return None, False, "Presupuesto diario de créditos agotado (se reparte el mes)", None
    ev = buscar_evento_odds(sport_key, local, visitante, inicio_utc, cache_eventos)
    if not ev:
        return None, False, "Evento no encontrado en The Odds API", None
    modelo = None
    if local_id is not None and visitante_id is not None and cache_stats is not None:
        modelo = calcular_modelo_estadistico(comp_code, local_id, visitante_id, cache_stats)
    datos = consultar_cuotas_evento(sport_key, ev.get("id"))
    if not datos:
        return None, False, "Sin respuesta de cuotas", None
    cands, n_casas, nota, fav, combo = generar_candidatos(datos, local, visitante, modelo)
    alertables = [c for c in cands if es_alertable(c)]
    if alertables:
        mejor = max(alertables, key=lambda c: c["score"])
    elif combo:
        mejor = combo
    elif cands:
        mejor = max(cands, key=lambda c: (c["confirmado_stats"], c["score"]))
    else:
        return None, True, nota, fav
    mejor["form_info"] = form_info
    if modelo is None:
        mejor["nota"] = "Sin datos estadísticos suficientes para confirmar"
    elif not es_alertable(mejor):
        mejor["nota"] = "El modelo estadístico no respalda la apuesta" if not mejor["confirmado_stats"] else "Ventaja inferior al mínimo"
    return mejor, True, mejor.get("nota"), fav


CLAVES_ANALISIS = ("mercado", "tipo_mercado", "categoria_visual", "equipo_pronosticado", "cuota", "prob_modelo", "stake",
                   "n_casas", "casa", "prob_mercado", "prob_estadistica", "confirmado_stats", "xg_local", "xg_visitante",
                   "sel", "cuota_ref", "cuota_minima", "sin_modelo_ok")


def reconstruir_analisis(prev, form_info):
    if not prev or not prev.get("tiene_pronostico") or not prev.get("mercado"):
        return None
    a = {k: prev.get(k) for k in CLAVES_ANALISIS}
    a["categoria_visual"] = prev.get("categoria_visual", "doble_oportunidad")
    a["ev"] = prev.get("ev_numero")
    a["form_info"] = form_info
    return a


AVISO_JUEGO = "🔞 <i>+18 • Juega con responsabilidad • Información estadística, no es asesoramiento • jugarbien.es</i>"


def enviar_telegram(mensaje, url_accion=None, texto_boton="📱 Abrir en Web App"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"{mensaje}\n\n{AVISO_JUEGO}",
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

FD_VENTANA = []   # marcas de tiempo de las últimas peticiones a football-data.org
MAX_REFRESCOS_ID = int(os.getenv("FD_MAX_REFRESCOS", "8"))
ESTADOS_CERRADOS = ("FINISHED", "FINALIZADO", "AWARDED", "CANCELLED", "POSTPONED")


def fd_get(url, **kw):
    """GET a football-data.org respetando el límite de 10 peticiones por minuto."""
    ahora = time.time()
    while FD_VENTANA and ahora - FD_VENTANA[0] > 60:
        FD_VENTANA.pop(0)
    if len(FD_VENTANA) >= 9:
        espera = 61 - (ahora - FD_VENTANA[0])
        if espera > 0:
            print(f"   ⏳ Límite football-data: esperando {espera:.0f}s")
            time.sleep(espera)
    FD_VENTANA.append(time.time())
    return requests.get(url, **kw)


def _minutos_desde_inicio(utc_str, ahora_utc):
    try:
        ini = datetime.fromisoformat((utc_str or "").replace("Z", "+00:00"))
        return (ahora_utc - ini).total_seconds() / 60.0
    except Exception:
        return None


def refrescar_partidos_atascados(partidos_raw, partidos_previos, ahora_utc):
    """Los listados por fecha de la API gratuita a veces tardan horas en actualizar resultados o dejan de
    devolver algún partido. Para los partidos que llevan más de 135 min sin cerrarse, o que han desaparecido
    del listado, se consulta la ficha individual (/matches/{id}) y se sustituye el dato antiguo.
    Devuelve un diccionario con contadores de diagnóstico."""
    diag = {"atascados": 0, "ausentes": 0, "refrescados": 0}
    presentes = {m.get("id"): m for m in partidos_raw if m.get("id")}
    candidatos = []   # (minutos desde el inicio, id)
    for m in partidos_raw:
        if m.get("status") in ESTADOS_CERRADOS:
            continue
        mins = _minutos_desde_inicio(m.get("utcDate"), ahora_utc)
        if mins is not None and mins > 135:
            candidatos.append((mins, m.get("id")))
            diag["atascados"] += 1
    for pv in partidos_previos:
        pid = pv.get("id")
        if pid in presentes or pv.get("estado") in ("FINISHED",):
            continue
        mins = _minutos_desde_inicio(pv.get("utcDate") or pv.get("hora_utc"), ahora_utc)
        if mins is not None and mins > 135:
            candidatos.append((mins, pid))
            diag["ausentes"] += 1
    candidatos.sort(reverse=True)
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    for mins, pid in candidatos[:MAX_REFRESCOS_ID]:
        try:
            res = fd_get(f"https://api.football-data.org/v4/matches/{pid}", headers=headers, timeout=12)
            if res.status_code != 200:
                print(f"   Aviso refresco partido {pid}: HTTP {res.status_code}")
                continue
            data = res.json()
            m = data if data.get("homeTeam") else (data.get("match") or {})
            if not m.get("homeTeam") or not m.get("id"):
                continue
            partidos_raw[:] = [x for x in partidos_raw if x.get("id") != m["id"]]
            partidos_raw.append(m)
            diag["refrescados"] += 1
            print(f"   🔄 Partido {pid} refrescado por ficha individual: {m.get('status')}")
        except Exception as e:
            print(f"   Aviso refresco partido {pid}: {e}")
    return diag


def obtener_partidos_por_rango(date_from, date_to):
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    print(f"📡 [Football-Data.org] Petición intervalo: {date_from} al {date_to}")
    for intento in range(3):
        try:
            res = fd_get(url, headers=headers, timeout=12)
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
        res_live = fd_get(url_live, headers=headers, timeout=10)
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
        if a.get("finalizado") and not a.get("push"):
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

def buscar_mejor_combinada(partidos, alertas):
    """Combinada de 2-3 selecciones de partidos distintos, todas en la MISMA casa. Cada selección sale del análisis
    del partido (cualquier mercado con respaldo estadístico, probabilidad >= 50%, cuota 1.25-2.30 y ventaja >= +1%).
    La combinada debe superar la ventaja y la probabilidad conjuntas mínimas."""
    usados = set()
    for a in alertas:
        if a.get("es_combinada"):
            usados.update(str(l.get("id")) for l in a.get("legs", []))
    por_casa = {}
    for p in partidos:
        fav = p.get("fav")
        if not fav or p.get("estado") not in ("TIMED", "SCHEDULED") or p.get("minutos_restantes", 0) < 10:
            continue
        if str(p.get("id")) in usados or p.get("telegram_enviado"):
            continue   # si el partido ya tiene su alerta individual, no se repite la exposición en una combinada
        for casa, patas in fav.get("por_casa", {}).items():
            if isinstance(patas, dict):   # formato antiguo: solo victoria del favorito
                patas = [{"mercado": f"Victoria {patas['equipo']} (1X2)", "tipo": "1X2", "sel": None, "equipo": patas["equipo"],
                          "cuota": patas["cuota"], "prob": patas["prob"], "ev": patas["ev"], "confirmado": patas.get("confirmado")}]
            mejor_leg = None
            for d in patas:
                if not (COMBI_CUOTA_PATA[0] <= d["cuota"] <= COMBI_CUOTA_PATA[1] and d["prob"] >= COMBI_PROB_PATA_MIN
                        and d["ev"] >= COMBI_EV_PATA_MIN and d.get("confirmado")):
                    continue
                score = d["ev"] * math.sqrt(d["prob"])
                if mejor_leg is None or score > mejor_leg["score"]:
                    mejor_leg = {"id": p.get("id"), "partido": f"{p.get('local')} vs {p.get('visitante')}", "equipo": d.get("equipo"),
                                 "mercado": d["mercado"], "tipo": d.get("tipo", "1X2"), "sel": d.get("sel"),
                                 "cuota": d["cuota"], "prob": d["prob"], "ev": d["ev"], "score": score,
                                 "timestamp_ms": p.get("timestamp_ms", 0), "fecha": p.get("fecha"),
                                 "fecha_hora_display": p.get("fecha_hora_display"), "liga": p.get("liga")}
            if mejor_leg:
                por_casa.setdefault(casa, []).append(mejor_leg)
    mejor = None
    for casa, legs in por_casa.items():
        legs = sorted(legs, key=lambda l: l["ev"], reverse=True)[:8]
        for k in range(2, COMBI_MAX_PATAS + 1):
            for combo in itertools.combinations(legs, k):
                cuota = math.prod(l["cuota"] for l in combo)
                prob = math.prod(l["prob"] for l in combo)
                ev = (prob * cuota - 1.0) * 100
                if prob < COMBI_PROB_MIN or ev < COMBI_EV_MIN:
                    continue
                score = ev * math.sqrt(prob)
                if mejor is None or score > mejor["score"]:
                    mejor = {"casa": casa, "legs": list(combo), "cuota": cuota, "prob": prob, "ev": ev, "score": score}
    return mejor


def crear_alerta_combinada(c, semana_id):
    legs = sorted(c["legs"], key=lambda l: l["timestamp_ms"])
    primero = legs[0]
    ids = "-".join(str(l["id"]) for l in legs)
    return {
        "id_partido": "",
        "id_alerta": f"COMBI_{semana_id}_{ids}",
        "partido": f"Combinada de partidos ×{len(legs)}",
        "mercado": " + ".join(l["mercado"] for l in legs),
        "tipo_mercado": "COMBINADA",
        "categoria_visual": "combinada",
        "es_combinada": True,
        "legs": [{"id": l["id"], "partido": l["partido"], "equipo": l["equipo"], "mercado": l["mercado"], "tipo": l["tipo"],
                  "sel": l["sel"], "cuota": l["cuota"], "fecha_hora_display": l["fecha_hora_display"],
                  "res": None, "marcador": None} for l in legs],
        "casa": c["casa"],
        "cuota": f"@{round(c['cuota'], 2)}",
        "ev": f"+{round(c['ev'], 1)}%",
        "prob_combinada": round(c["prob"] * 100, 1),
        "stake": "1/10",
        "hora": first_hora(primero),
        "fecha": primero["fecha"],
        "fecha_hora_display": primero["fecha_hora_display"],
        "semana_id": semana_id,
        "es_ht": False,
        "es_semana_actual": True,
        "estado_partido": "TIMED",
        "marcador": None,
        "marcador_final": None,
        "finalizado": False,
        "acertado": None,
        "liquidada_telegram": False,
        "cuotas_reales": True,
    }


def first_hora(leg):
    txt = leg.get("fecha_hora_display") or ""
    return txt.split("•")[-1].strip() if "•" in txt else txt


def mensaje_combinada(a):
    lineas = []
    for i, l in enumerate(a["legs"], 1):
        lineas.append(f"{i}️⃣ <b>{l.get('mercado') or 'Victoria ' + str(l['equipo'])}</b> — {l['partido']} ({l['fecha_hora_display']}) @{l['cuota']}")
    return (
        f"🎯 <b>COMBINADA DE PARTIDOS (+EV) ×{len(a['legs'])}</b>\n\n"
        + "\n".join(lineas) + "\n\n"
        f"🏦 <b>Casa:</b> {a['casa']} (todas las selecciones en la misma casa)\n"
        f"💰 <b>Cuota total:</b> {a['cuota']}\n"
        f"📈 <b>Ventaja combinada (+EV):</b> {a['ev']}\n"
        f"🎲 <b>Probabilidad de acierto:</b> {a['prob_combinada']}% (deben acertar todas)\n"
        f"💡 <b>Stake Sugerido:</b> {a['stake']} unidades\n\n"
        f"⚡ <i>Apex Quant Engine • Combinada con respaldo estadístico</i>"
    )


def liquidar_combinadas(alertas, mapa_por_id):
    for a in alertas:
        if not a.get("es_combinada") or a.get("finalizado"):
            continue
        legs = a.get("legs", [])
        aciertos, pendientes, fallo, en_juego = 0, 0, False, False
        for leg in legs:
            info = mapa_por_id.get(str(leg.get("id")))
            if not info:
                pendientes += 1
                continue
            if info["estado"] == "FINISHED" and info["goles_local"] is not None and info["goles_visitante"] is not None:
                ok = evaluar_pick(leg.get("sel"), leg.get("mercado") or f"Victoria {leg.get('equipo')} (1X2)", leg.get("tipo", "1X2"),
                                  info["goles_local"], info["goles_visitante"], info.get("ht_local"), info.get("ht_visitante"),
                                  nombre_local=info["local"], nombre_visitante=info["visitante"],
                                  equipo_pronosticado=leg.get("equipo"))
                leg["marcador"] = info["marcador"]
                if ok is True:
                    leg["res"] = True
                    aciertos += 1
                elif ok is False:
                    leg["res"] = False
                    fallo = True
                else:
                    pendientes += 1   # sin datos suficientes todavía
                    continue
            else:
                pendientes += 1
                if info["estado"] in ("IN_PLAY", "HT", "PAUSED"):
                    en_juego = True
        if fallo or pendientes == 0:
            a["finalizado"] = True
            a["acertado"] = (not fallo) and pendientes == 0
            a["marcador_final"] = f"{aciertos}/{len(legs)} aciertos"
            a["estado_partido"] = "FINISHED"
            if not a.get("liquidada_telegram"):
                detalle = "\n".join(
                    f"{'✅' if l.get('res') else ('❌' if l.get('res') is False else '⏳')} {l.get('mercado') or l.get('equipo')} ({l['partido']}) {l.get('marcador') or ''}".rstrip()
                    for l in legs)
                titulo = "✅ <b>Resultado:</b> ACERTADA" if a["acertado"] else "❌ <b>Resultado:</b> PERDIDA"
                enviar_telegram(
                    f"🎯 <b>COMBINADA DE PARTIDOS ×{len(legs)}</b>\n{detalle}\n\n{titulo}\n"
                    f"💰 <b>Cuota:</b> {a['cuota']} • 💡 <b>Stake:</b> {a['stake']}\n\n⚡ <i>Apex Quant Engine</i>",
                    url_accion=APP_URL, texto_boton="📱 Ver en la Web App")
                a["liquidada_telegram"] = True
        elif en_juego or aciertos > 0:
            a["estado_partido"] = "IN_PLAY"


ARCHIVO_LEDGER = "historico_picks.json"


def _a_float(txt, defecto):
    try:
        return float(str(txt).split("/")[0].replace("@", "").replace("U", "").replace("+", "").replace("%", "").strip())
    except Exception:
        return defecto


def actualizar_ledger(alertas, partidos):
    """Libro mayor permanente (no se reinicia los lunes) con todas las picks liquidadas con cuotas reales:
    grupo TG = alertas enviadas a Telegram; grupo CONTROL = picks analizadas y descartadas."""
    ledger = {"version": 1, "picks": []}
    if os.path.exists(ARCHIVO_LEDGER):
        try:
            with open(ARCHIVO_LEDGER, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        except Exception:
            ledger = {"version": 1, "picks": []}
    picks = ledger.get("picks", [])
    ids = {p.get("id") for p in picks}
    nuevas = 0

    for a in alertas:
        if not (a.get("finalizado") and a.get("acertado") is not None and a.get("cuotas_reales") and not a.get("push")):
            continue
        es_combi = bool(a.get("es_combinada"))
        pid = str(a.get("id_alerta")) if es_combi else f"TG_{a.get('id_alerta')}"
        if pid in ids:
            continue
        picks.append({"id": pid, "grupo": "COMBI" if es_combi else "TG", "fecha": a.get("fecha"), "mes": (a.get("fecha") or "")[:7],
                      "semana_id": a.get("semana_id"), "partido": a.get("partido"), "mercado": a.get("mercado"),
                      "casa": a.get("casa"), "cuota": _a_float(a.get("cuota"), 2.0), "stake": _a_float(a.get("stake"), 1.0),
                      "ev": _a_float(a.get("ev"), 0.0), "confirmado_stats": a.get("confirmado_stats"),
                      "acertado": bool(a.get("acertado")), "marcador": a.get("marcador_final")})
        ids.add(pid)
        nuevas += 1

    for p in partidos:
        if not (p.get("estado") == "FINISHED" and p.get("acertado") is not None and p.get("tiene_pronostico")
                and p.get("analizado") and not p.get("telegram_enviado")):
            continue
        pid = f"CTRL_{p.get('id')}_{p.get('tipo_mercado')}"
        if pid in ids:
            continue
        picks.append({"id": pid, "grupo": "CONTROL", "fecha": p.get("fecha"), "mes": (p.get("fecha") or "")[:7],
                      "semana_id": p.get("semana_id"), "partido": f"{p.get('local')} vs {p.get('visitante')}",
                      "mercado": p.get("mercado"), "casa": p.get("casa"), "cuota": _a_float(p.get("cuota"), 2.0),
                      "stake": _a_float(p.get("stake"), 1.0), "ev": _a_float(p.get("ev_numero"), 0.0),
                      "confirmado_stats": p.get("confirmado_stats"), "acertado": bool(p.get("acertado")),
                      "marcador": p.get("marcador")})
        ids.add(pid)
        nuevas += 1

    if nuevas:
        ledger["picks"] = picks
        try:
            with open(ARCHIVO_LEDGER, "w", encoding="utf-8") as f:
                json.dump(ledger, f, ensure_ascii=False, separators=(",", ":"))
            print(f"📒 Libro mayor actualizado: +{nuevas} picks liquidadas (total {len(picks)})")
        except Exception as e:
            print(f"Aviso guardando libro mayor: {e}")


COMPS_FORMA = ["PL", "PD", "BL1", "SA", "FL1", "CL"]
FORMAS_TTL_MIN = int(os.getenv("FORMAS_TTL_MIN", "90"))


def calcular_formas(cache_stats):
    """Últimos 5 resultados REALES de cada equipo (liga + Champions), del más antiguo al más reciente."""
    por_equipo = {}
    for comp in COMPS_FORMA:
        f = obtener_fuerzas_liga(comp, cache_stats)
        if not f:
            continue
        for utc, hid, aid, gh, ga in f.get("res", []):
            r_h = "W" if gh > ga else ("L" if gh < ga else "D")
            r_a = "L" if gh > ga else ("W" if gh < ga else "D")
            por_equipo.setdefault(hid, []).append((utc, r_h))
            por_equipo.setdefault(aid, []).append((utc, r_a))
    formas = {}
    for tid, lst in por_equipo.items():
        lst.sort(key=lambda x: x[0])
        formas[str(tid)] = "-".join(r for _, r in lst[-5:])
    return formas


def actualizar_formas(formas_prev, cache_stats, ahora_utc):
    """Reutiliza la forma guardada si es reciente; si no, la recalcula con los resultados de la temporada."""
    try:
        t = datetime.fromisoformat((formas_prev or {}).get("t", "").replace("Z", "+00:00"))
        if formas_prev.get("e") and (ahora_utc - t).total_seconds() < FORMAS_TTL_MIN * 60:
            return formas_prev
    except Exception:
        pass
    nuevas = calcular_formas(cache_stats)
    if nuevas:
        print(f"📈 Forma real recalculada para {len(nuevas)} equipos")
        return {"t": ahora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "e": nuevas}
    return formas_prev or {"t": "", "e": {}}


def construir_form_info(formas, hid, aid):
    rl, rv = formas.get(str(hid)), formas.get(str(aid))
    if not rl or not rv or len(rl.split("-")) < 3 or len(rv.split("-")) < 3:
        return {"ajuste_prob": 0.0, "racha_local": rl or "", "racha_visitante": rv or "", "tendencia": "",
                "resumen": "Sin datos de forma suficientes", "diferencia_forma": 0,
                "es_club_top_local": False, "es_club_top_vis": False, "real": False}

    def pts(r):
        return sum(3 if c == "W" else (1 if c == "D" else 0) for c in r.split("-"))

    pl, pv = pts(rl), pts(rv)
    dif = pl - pv
    if dif >= 5:
        tendencia = "🔥 Racha Favorable Local (+Dinámica)"
    elif dif <= -5:
        tendencia = "🔥 Racha Favorable Visitante (+Dinámica)"
    elif dif <= -3:
        tendencia = "⚠️ Visitante en Alza (+Dinámica)"
    elif dif >= 3:
        tendencia = "⚖️ Ligera Ventaja Local"
    elif dif <= -1:
        tendencia = "⚖️ Ligera Ventaja Visitante"
    else:
        tendencia = "⚖️ Tendencia Equilibrada"
    return {"ajuste_prob": 0.0, "racha_local": rl, "racha_visitante": rv, "tendencia": tendencia,
            "resumen": f"Local: {rl} ({pl} pts) vs Vis: {rv} ({pv} pts)", "diferencia_forma": dif,
            "es_club_top_local": False, "es_club_top_vis": False, "real": True}


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
    preparar_presupuesto(datos_previos, ahora_madrid)
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
    partidos_api_n = len(partidos_raw)
    diag_refresco = refrescar_partidos_atascados(partidos_raw, partidos_previos, ahora_utc)
    print(f"🩺 Diagnóstico partidos: API={partidos_api_n} | atascados={diag_refresco['atascados']} | "
          f"ausentes={diag_refresco['ausentes']} | refrescados por ficha={diag_refresco['refrescados']}")

    partidos_para_web = []
    partidos_map_por_id = {}
    partidos_map_por_nombres = {}
    partidos_previos_map = {str(x.get('id')): x for x in partidos_previos}
    cache_eventos_odds = {}
    cache_stats_liga = {}
    formas_equipos = actualizar_formas(datos_previos.get("formas_equipos"), cache_stats_liga, ahora_utc)

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
            "ht_local": half_time.get("home"),
            "ht_visitante": half_time.get("away"),
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

        form_info = construir_form_info(formas_equipos.get("e", {}), home_team_data.get("id"), away_team_data.get("id"))
        prev = partidos_previos_map.get(str(p.get("id")))
        analizado = bool(prev and prev.get("analizado"))
        nota_cuotas = prev.get("nota_cuotas") if prev else None
        analisis = None
        analisis_nuevo = False
        fav_info = prev.get("fav") if (prev and prev.get("analizado")) else None

        if analizado:
            analisis = reconstruir_analisis(prev, form_info)
        elif (not es_finalizado) and (not es_en_juego) and VENTANA_MIN <= minutos_restantes <= VENTANA_MAX:
            inicio_dt = datetime.fromtimestamp(timestamp_inicio_ms / 1000.0, timezone.utc) if timestamp_inicio_ms else None
            analisis, definitivo, nota, fav_nuevo = analizar_partido_con_cuotas(comp_code, nombre_local, nombre_visitante, inicio_dt, form_info, cache_eventos_odds, home_team_data.get("id"), away_team_data.get("id"), cache_stats_liga)
            nota_cuotas = nota
            if definitivo:
                analizado = True
                analisis_nuevo = analisis is not None
                fav_info = fav_nuevo
            else:
                analisis = None

        acertado_partido = None
        push_partido = False
        id_alerta_unica = None
        ya_registrada = False
        if analisis:
            if es_finalizado and goles_local is not None and goles_visitante is not None:
                res_pick = evaluar_pick(
                    analisis.get("sel"), analisis["mercado"], analisis["tipo_mercado"],
                    goles_local, goles_visitante, half_time.get("home"), half_time.get("away"),
                    nombre_local=nombre_local, nombre_visitante=nombre_visitante,
                    equipo_pronosticado=analisis.get("equipo_pronosticado")
                )
                if res_pick == "PUSH":
                    push_partido = True
                elif res_pick is True or res_pick is False:
                    acertado_partido = res_pick
            id_alerta_unica = f"{p.get('id')}_{analisis['tipo_mercado']}"
            ya_registrada = any(a.get("id_alerta") == id_alerta_unica or (a.get("partido") == partido_nombre and a.get("tipo_mercado") == analisis["tipo_mercado"]) for a in alertas_acumuladas)

        fue_enviado_telegram = False

        # ALERTA OFICIAL: mejor cuota real entre las casas objetivo con +EV >= 3% frente al consenso (T-90m a T-15m)
        if analisis_nuevo and analisis["ev"] >= EV_MINIMO_PCT and (analisis.get("confirmado_stats") or analisis.get("sin_modelo_ok") or not STATS_OBLIGATORIAS) and not ya_registrada:
            fue_enviado_telegram = True
            if analisis.get("cuota_minima"):
                linea_cuota = (f"💰 <b>Cuota mínima para tener valor:</b> @{analisis['cuota']} "
                               f"(referencia ≈ @{analisis.get('cuota_ref')}). Comprueba el precio real en «Crear apuesta»; si es menor, no la juegues.\n")
            else:
                linea_cuota = f"💰 <b>Cuota {analisis.get('casa', '')}:</b> @{analisis['cuota']}\n"
            alerta_msg = (
                f"🎯 <b>ALERTA CUANTITATIVA (+EV) — [PRE-PARTIDO]</b>\n\n"
                f"🏆 <b>Competición:</b> {comp_info['name']}\n"
                f"⚽ <b>Partido:</b> {partido_nombre}\n"
                f"⏰ <b>Inicio:</b> {fecha_hora_display} (en {minutos_restantes} min)\n"
                f"{analisis.get('icono_tg', '🛡️')} <b>Mercado:</b> {analisis['mercado']}\n"
                f"{linea_cuota}"
                f"📈 <b>Ventaja (+EV vs consenso):</b> +{analisis['ev']}%\n"
                f"💡 <b>Stake Sugerido:</b> {analisis['stake']}/10 unidades\n"
                f"🧮 <b>Prob. combinada:</b> {analisis['prob_modelo']} (mercado {analisis.get('prob_mercado') if analisis.get('prob_mercado') is not None else '—'}% · modelo {analisis.get('prob_estadistica') if analisis.get('prob_estadistica') is not None else '—'}%)\n"
                f"📐 <b>Respaldo estadístico:</b> {'✅ sí' if analisis.get('confirmado_stats') else '—'} • xG {analisis.get('xg_local')} - {analisis.get('xg_visitante')} • consenso de {analisis.get('n_casas', '?')} casas\n"
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
                "sel": analisis.get("sel"),
                "cuota_ref": analisis.get("cuota_ref"),
                "cuota_minima": analisis.get("cuota_minima"),
                "cuotas_reales": True,
                "confirmado_stats": analisis.get("confirmado_stats"),
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
            "sel": analisis.get("sel") if tiene_pron else None,
            "cuota_ref": analisis.get("cuota_ref") if tiene_pron else None,
            "cuota_minima": analisis.get("cuota_minima") if tiene_pron else None,
            "sin_modelo_ok": analisis.get("sin_modelo_ok") if tiene_pron else None,
            "ht_local": half_time.get("home"),
            "ht_visitante": half_time.get("away"),
            "push": push_partido,
            "prob_mercado": analisis.get("prob_mercado") if tiene_pron else None,
            "prob_estadistica": analisis.get("prob_estadistica") if tiene_pron else None,
            "confirmado_stats": analisis.get("confirmado_stats") if tiene_pron else None,
            "xg_local": analisis.get("xg_local") if tiene_pron else None,
            "xg_visitante": analisis.get("xg_visitante") if tiene_pron else None,
            "tiene_pronostico": tiene_pron,
            "analizado": analizado,
            "nota_cuotas": nota_cuotas,
            "fav": fav_info,
            "semana_id": semana_actual_id,
            "telegram_enviado": bool(fue_enviado_telegram or ya_registrada or (prev and prev.get("telegram_enviado"))),
            "es_empate_ht": False,
            "acertado": acertado_partido,
            "form_info": form_info
        }
        partidos_para_web.append(item)

    # Un partido ya finalizado no puede "retroceder" a programado/en juego por un dato atrasado de la API
    for i, it in enumerate(partidos_para_web):
        pv = partidos_previos_map.get(str(it.get("id")))
        if pv and pv.get("estado") == "FINISHED" and it.get("estado") != "FINISHED" and pv.get("marcador"):
            restaurado = dict(pv)
            restaurado["minutos_restantes"] = it.get("minutos_restantes")
            restaurado["telegram_enviado"] = bool(pv.get("telegram_enviado") or it.get("telegram_enviado"))
            partidos_para_web[i] = restaurado

    # COMBINADAS DE FAVORITOS (máx. 3 partidos, misma casa, +EV conjunto y respaldo estadístico)
    if COMBI_ACTIVA:
        mejor_combi = buscar_mejor_combinada(partidos_para_web, alertas_acumuladas)
        if mejor_combi:
            alerta_combi = crear_alerta_combinada(mejor_combi, semana_actual_id)
            if not any(a.get("id_alerta") == alerta_combi["id_alerta"] for a in alertas_acumuladas):
                enviar_telegram(mensaje_combinada(alerta_combi), url_accion=APP_URL, texto_boton="📱 Abrir en Web App")
                alertas_acumuladas.append(alerta_combi)
                print(f"🎯 Combinada creada: {alerta_combi['mercado']} {alerta_combi['cuota']} (EV {alerta_combi['ev']})")

    # RECONCILIACIÓN Y LIQUIDACIÓN
    liquidar_combinadas(alertas_acumuladas, partidos_map_por_id)
    for alerta in alertas_acumuladas:
        if alerta.get("es_combinada"):
            continue
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
                
                res_pick = evaluar_pick(
                    alerta.get("sel"), alerta["mercado"], alerta.get("tipo_mercado", ""), g_loc, g_vis,
                    partido_encontrado.get("ht_local"), partido_encontrado.get("ht_visitante"),
                    nombre_local=partido_encontrado["local"], nombre_visitante=partido_encontrado["visitante"],
                    equipo_pronosticado=alerta.get("equipo_pronosticado")
                )
                if res_pick is None:
                    continue   # falta algún dato (p. ej. el marcador del descanso): se reintenta en el siguiente ciclo
                alerta["finalizado"] = True
                alerta["marcador_final"] = marcador_fin
                alerta["goles_local"] = g_loc
                alerta["goles_visitante"] = g_vis
                es_push = (res_pick == "PUSH")
                acertado = None if es_push else bool(res_pick)
                alerta["acertado"] = acertado
                alerta["push"] = es_push

                if not alerta.get("liquidada_telegram"):
                    nombre_partido_display = p_nombre or f"{partido_encontrado['local']} vs {partido_encontrado['visitante']}"
                    if es_push:
                        msg_settle = (
                            f"⚽ <b>{nombre_partido_display}</b>\n"
                            f"📌 <b>Pronóstico:</b> {alerta['mercado']}\n"
                            f"↩️ <b>Resultado:</b> DEVUELTA (push)\n"
                            f"🏁 <b>Marcador Final:</b> {marcador_fin or 'Final'}\n\n"
                            f"⚡ <i>Apex Quant Engine</i>"
                        )
                    elif acertado:
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
        "ultima_actualizacion_utc": ahora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        "creditos_dia": ODDS_ESTADO.get("dia"),
        "formas_equipos": formas_equipos,
        "diagnostico": {"perfil_mercados": ODDS_ESTADO.get("perfil"), "presupuesto_dia": (round(ODDS_ESTADO["presupuesto_dia"], 1) if ODDS_ESTADO.get("presupuesto_dia") else None), "partidos_api": partidos_api_n, "atascados": diag_refresco["atascados"],
                        "ausentes": diag_refresco["ausentes"], "refrescados": diag_refresco["refrescados"]},
        "alertas": alertas_acumuladas[-70:]
    }

    actualizar_ledger(alertas_acumuladas, partidos_guardar)

    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump(datos_completos, f, ensure_ascii=False, indent=2)

    total_fin = sum(1 for p in partidos_guardar if p.get("estado") == "FINISHED")
    print(f"💳 The Odds API: {ODDS_ESTADO['consultas']} consultas de cuotas en este ciclo | créditos restantes: {ODDS_ESTADO['restantes']}")
    print(f"📁 datos.json guardado. Partidos semana: {len(partidos_guardar)} (Finalizados: {total_fin}) | Alertas: {len(alertas_acumuladas)} | Semana: {semana_guardada}")

if __name__ == "__main__":
    ejecutar_ciclo()
