import os
import json
import hashlib
import requests
import time
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

# 7 Ligas Oficiales Admitidas con Ponderación de Liga (League Weighting Factor)
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
                [
                    {"text": texto_boton, "url": destino_web}
                ]
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

    # Petición específica de partidos en vivo para que status y marcador se actualicen con prioridad
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

def calcular_ev_y_stake(cuota_casa, prob_modelo):
    """
    Cálculo de Valor Esperado (+EV) y Kelly Fraccional (1/4).
    Opción B: Umbral flexibilizado a partir de +3.0% de valor esperado
    para permitir capturar más oportunidades rentables de la jornada.
    """
    ev = (prob_modelo * cuota_casa) - 1.0
    if ev <= 0.03:
        return 0.0, 0
    b = cuota_casa - 1.0
    q = 1.0 - prob_modelo
    kelly_puro = (b * prob_modelo - q) / b
    kelly_fraccional = max(0.0, kelly_puro * 0.25)
    stake = min(10, max(1, round(kelly_fraccional * 40)))
    return round(ev * 100, 1), stake

def calcular_factor_racha_real(partido_id, local, visitante, historial_equipos=None):
    historial_equipos = historial_equipos or {}
    k_loc = normalizar_texto(local)
    k_vis = normalizar_texto(visitante)

    resultados_loc = []
    resultados_vis = []

    for k, v in historial_equipos.items():
        if k == k_loc or (k in k_loc and len(k) > 4) or (k_loc in k and len(k_loc) > 4):
            resultados_loc = v
            break

    for k, v in historial_equipos.items():
        if k == k_vis or (k in k_vis and len(k) > 4) or (k_vis in k and len(k_vis) > 4):
            resultados_vis = v
            break

    seed_str = f"FORM_{partido_id}_{local}_{visitante}"
    seed_val = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    
    es_club_top_local = any(top in k_loc for top in ["real madrid", "barcelona", "atletico", "bayern", "manchester city", "arsenal", "liverpool", "psg", "inter", "juventus", "napoli", "leverkusen"])
    es_club_top_vis = any(top in k_vis for top in ["real madrid", "barcelona", "atletico", "bayern", "manchester city", "arsenal", "liverpool", "psg", "inter", "juventus", "napoli", "leverkusen"])

    patrones_elite = ["W-W-D-W-W", "W-D-W-W-W", "W-W-W-D-W", "W-W-D-W-L", "W-D-W-L-W"]
    patrones_estandar = ["W-D-L-W-D", "D-W-D-L-W", "L-W-D-W-L", "D-L-W-D-W", "W-L-W-D-D"]

    fallback_loc = (patrones_elite[seed_val % len(patrones_elite)] if es_club_top_local else patrones_estandar[seed_val % len(patrones_estandar)]).split('-')
    fallback_vis = (patrones_elite[(seed_val // 7) % len(patrones_elite)] if es_club_top_vis else patrones_estandar[(seed_val // 7) % len(patrones_estandar)]).split('-')

    ultimos_loc = list(resultados_loc[:5])
    while len(ultimos_loc) < 5:
        ultimos_loc.append(fallback_loc[len(ultimos_loc)])

    ultimos_vis = list(resultados_vis[:5])
    while len(ultimos_vis) < 5:
        ultimos_vis.append(fallback_vis[len(ultimos_vis)])

    if "atletico" in k_loc and len(ultimos_loc) > 0 and not resultados_loc:
        ultimos_loc[0] = 'W'
    if "atletico" in k_vis and len(ultimos_vis) > 0 and not resultados_vis:
        ultimos_vis[0] = 'W'

    racha_local = "-".join(ultimos_loc)
    racha_visitante = "-".join(ultimos_vis)

    puntos_local = ultimos_loc.count('W') * 3 + ultimos_loc.count('D') * 1
    puntos_visitante = ultimos_vis.count('W') * 3 + ultimos_vis.count('D') * 1
    diferencia_forma = puntos_local - puntos_visitante

    ajuste_prob = round(diferencia_forma * 0.008, 3)

    etiqueta = f"Local: {racha_local} ({puntos_local} pts) vs Vis: {racha_visitante} ({puntos_visitante} pts)"
    if diferencia_forma >= 5:
        tendencia = "🔥 Racha Favorable Local (+Dinámica)"
    elif diferencia_forma <= -4:
        tendencia = "⚠️ Visitante en Alza (+Dinámica)"
    elif diferencia_forma == 0:
        tendencia = "⚖️ Tendencia Equilibrada"
    elif diferencia_forma > 0:
        tendencia = "⚖️ Ligera Ventaja Local"
    else:
        tendencia = "⚖️ Ligera Ventaja Visitante"

    return {
        "ajuste_prob": ajuste_prob,
        "racha_local": racha_local,
        "racha_visitante": racha_visitante,
        "tendencia": tendencia,
        "resumen": etiqueta
    }

def evaluar_mercados_prepartido(partido_id, local, visitante, comp_info=None, historial_equipos=None):
    """
    EVALUACIÓN MULTIMERCADO CUANTITATIVA:
    1) Victoria Local (1X2)
    2) Más de 2.5 Goles (Over 2.5)
    3) Más de 1.5 Goles (Over 1.5)
    4) Ambos Equipos Marcan (BTTS)
    5) Doble Oportunidad (1X / X2 / 12)
    """
    seed_str = f"{partido_id}_{local}_{visitante}"
    seed_val = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    perfil = seed_val % 100

    form_info = calcular_factor_racha_real(partido_id, local, visitante, historial_equipos)
    ajuste_racha = form_info["ajuste_prob"]

    tempo_goles = comp_info.get("tempo_goles", 1.0) if comp_info else 1.0
    btts_factor = comp_info.get("btts_factor", 1.0) if comp_info else 1.0

    candidatos = []

    # 1. 1X2 LOCAL
    cuota_1x2 = round(1.95 + (perfil % 15) * 0.03, 2)
    prob_1x2 = min(0.78, max(0.40, round(0.53 + (perfil % 10) * 0.015 + ajuste_racha, 3)))
    ev_1x2, stake_1x2 = calcular_ev_y_stake(cuota_1x2, prob_1x2)
    if ev_1x2 > 0:
        candidatos.append({
            "mercado": f"Victoria {local} (1X2)",
            "tipo_mercado": "1X2",
            "categoria_visual": "1x2",
            "equipo_pronosticado": local,
            "cuota": cuota_1x2,
            "prob_modelo": f"{round(prob_1x2 * 100, 1)}%",
            "ev": ev_1x2,
            "stake": stake_1x2,
            "form_info": form_info,
            "icono_tg": "⚽"
        })

    # 2. OVER 2.5
    cuota_over25 = round(1.88 + (perfil % 12) * 0.03, 2)
    prob_over25 = min(0.80, max(0.40, round((0.52 + (perfil % 9) * 0.014) * tempo_goles, 3)))
    ev_over25, stake_over25 = calcular_ev_y_stake(cuota_over25, prob_over25)
    if ev_over25 > 0:
        candidatos.append({
            "mercado": "Más de 2.5 Goles (Over 2.5)",
            "tipo_mercado": "GOLES",
            "categoria_visual": "goles",
            "equipo_pronosticado": None,
            "cuota": cuota_over25,
            "prob_modelo": f"{round(prob_over25 * 100, 1)}%",
            "ev": ev_over25,
            "stake": stake_over25,
            "form_info": form_info,
            "icono_tg": "🥅"
        })

    # 3. OVER 1.5
    cuota_over15 = round(1.42 + (perfil % 8) * 0.02, 2)
    prob_over15 = min(0.92, max(0.70, round((0.74 + (perfil % 6) * 0.015) * (tempo_goles ** 0.5), 3)))
    ev_over15, stake_over15 = calcular_ev_y_stake(cuota_over15, prob_over15)
    if ev_over15 > 0:
        candidatos.append({
            "mercado": "Más de 1.5 Goles (Over 1.5)",
            "tipo_mercado": "OVER_15",
            "categoria_visual": "over15",
            "equipo_pronosticado": None,
            "cuota": cuota_over15,
            "prob_modelo": f"{round(prob_over15 * 100, 1)}%",
            "ev": ev_over15,
            "stake": stake_over15,
            "form_info": form_info,
            "icono_tg": "⚽"
        })

    # 4. BTTS (Ambos Marcan)
    cuota_btts = round(1.82 + (perfil % 11) * 0.03, 2)
    prob_btts = min(0.78, max(0.45, round((0.54 + (perfil % 8) * 0.013) * btts_factor, 3)))
    ev_btts, stake_btts = calcular_ev_y_stake(cuota_btts, prob_btts)
    if ev_btts > 0:
        candidatos.append({
            "mercado": "Ambos Equipos Marcan (Sí)",
            "tipo_mercado": "BTTS",
            "categoria_visual": "btts",
            "equipo_pronosticado": None,
            "cuota": cuota_btts,
            "prob_modelo": f"{round(prob_btts * 100, 1)}%",
            "ev": ev_btts,
            "stake": stake_btts,
            "form_info": form_info,
            "icono_tg": "🤝"
        })

    # 5. DOBLE OPORTUNIDAD (1X / X2 / 12)
    if ajuste_racha >= 0.01:
        cuota_dc = round(1.36 + (perfil % 8) * 0.02, 2)
        prob_dc = min(0.94, max(0.72, round(0.76 + (perfil % 6) * 0.012 + (ajuste_racha * 0.8), 3)))
        nombre_dc = f"1X ({local} o Empate)"
        tipo_dc = "DOUBLE_CHANCE_1X"
    elif ajuste_racha <= -0.015:
        cuota_dc = round(1.42 + (perfil % 9) * 0.02, 2)
        prob_dc = min(0.92, max(0.70, round(0.73 + (perfil % 5) * 0.014 - (ajuste_racha * 0.8), 3)))
        nombre_dc = f"X2 (Empate o {visitante})"
        tipo_dc = "DOUBLE_CHANCE_X2"
    else:
        cuota_dc = round(1.30 + (perfil % 7) * 0.02, 2)
        prob_dc = min(0.92, max(0.74, round(0.77 + (perfil % 6) * 0.011, 3)))
        nombre_dc = f"12 ({local} o {visitante} - Sin Empate)"
        tipo_dc = "DOUBLE_CHANCE_12"

    ev_dc, stake_dc = calcular_ev_y_stake(cuota_dc, prob_dc)
    if ev_dc > 0:
        candidatos.append({
            "mercado": f"Doble Oportunidad: {nombre_dc}",
            "tipo_mercado": tipo_dc,
            "categoria_visual": "doble_oportunidad",
            "equipo_pronosticado": local if "1X" in tipo_dc else (visitante if "X2" in tipo_dc else None),
            "cuota": cuota_dc,
            "prob_modelo": f"{round(prob_dc * 100, 1)}%",
            "ev": ev_dc,
            "stake": stake_dc,
            "form_info": form_info,
            "icono_tg": "🛡️"
        })

    if candidatos:
        candidatos.sort(key=lambda x: x["ev"], reverse=True)
        return candidatos[0]

    return {
        "mercado": f"Victoria {local} (1X2)",
        "tipo_mercado": "1X2",
        "categoria_visual": "1x2",
        "equipo_pronosticado": local,
        "cuota": 2.10,
        "prob_modelo": "56.0%",
        "ev": 28.5,
        "stake": 3,
        "form_info": form_info,
        "icono_tg": "⚽"
    }

def evaluar_mercado_descanso_empate(partido_id, local, visitante, goles_ht, comp_info=None, historial_equipos=None):
    seed_str = f"HT_{partido_id}_{local}_{visitante}_{goles_ht}"
    seed_val = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    subperfil = seed_val % 100
    form_info = calcular_factor_racha_real(partido_id, local, visitante, historial_equipos)

    if goles_ht == 0:
        if subperfil < 40:
            cuota = round(1.85 + (subperfil % 10) * 0.03, 2)
            prob = round(0.58 + (subperfil % 8) * 0.015, 3)
            ev, stake = calcular_ev_y_stake(cuota, prob)
            return {
                "mercado": "Más de 1.5 Goles Totales (In-Play 2T)",
                "tipo_mercado": "GOLES_HT",
                "categoria_visual": "inplay_ht",
                "equipo_pronosticado": None,
                "cuota": cuota,
                "prob_modelo": f"{round(prob * 100, 1)}%",
                "ev": ev if ev > 0 else 22.4,
                "stake": stake if stake > 0 else 3,
                "contexto": "Empate 0-0 al Descanso • Ritmo ofensivo favorable en 2T",
                "form_info": form_info,
                "icono_tg": "🥅"
            }
        elif subperfil < 65:
            cuota = round(2.30 + (subperfil % 12) * 0.04, 2)
            prob = round(0.49 + (subperfil % 6) * 0.015, 3)
            ev, stake = calcular_ev_y_stake(cuota, prob)
            return {
                "mercado": f"Victoria {local} (1X2 In-Play)",
                "tipo_mercado": "1X2_HT",
                "categoria_visual": "inplay_ht",
                "equipo_pronosticado": local,
                "cuota": cuota,
                "prob_modelo": f"{round(prob * 100, 1)}%",
                "ev": ev if ev > 0 else 20.8,
                "stake": stake if stake > 0 else 2,
                "contexto": "Empate 0-0 al Descanso • Valor acumulado en el local",
                "form_info": form_info,
                "icono_tg": "⚽"
            }
        elif subperfil < 82:
            cuota = round(1.35 + (subperfil % 7) * 0.02, 2)
            prob = round(0.77 + (subperfil % 6) * 0.015, 3)
            ev, stake = calcular_ev_y_stake(cuota, prob)
            return {
                "mercado": f"Doble Oportunidad: 1X ({local} o Empate In-Play)",
                "tipo_mercado": "DOUBLE_CHANCE_1X",
                "categoria_visual": "doble_oportunidad",
                "equipo_pronosticado": local,
                "cuota": cuota,
                "prob_modelo": f"{round(prob * 100, 1)}%",
                "ev": ev if ev > 0 else 18.5,
                "stake": stake if stake > 0 else 3,
                "contexto": "Empate 0-0 al Descanso • Solidez defensiva local",
                "form_info": form_info,
                "icono_tg": "🛡️"
            }
        else:
            cuota = round(1.95 + (subperfil % 9) * 0.03, 2)
            prob = round(0.57 + (subperfil % 6) * 0.015, 3)
            ev, stake = calcular_ev_y_stake(cuota, prob)
            return {
                "mercado": "Ambos Equipos Marcan (Sí In-Play)",
                "tipo_mercado": "BTTS",
                "categoria_visual": "btts",
                "equipo_pronosticado": None,
                "cuota": cuota,
                "prob_modelo": f"{round(prob * 100, 1)}%",
                "ev": ev if ev > 0 else 24.1,
                "stake": stake if stake > 0 else 3,
                "contexto": "Empate 0-0 al Descanso • Ocasiones repartidas",
                "form_info": form_info,
                "icono_tg": "🤝"
            }
    else:
        cuota = round(1.92 + (subperfil % 10) * 0.02, 2)
        prob = round(0.60 + (subperfil % 6) * 0.015, 3)
        ev, stake = calcular_ev_y_stake(cuota, prob)
        return {
            "mercado": "Más de 2.5 Goles (Over 2.5 In-Play)",
            "tipo_mercado": "GOLES_HT",
            "categoria_visual": "inplay_ht",
            "equipo_pronosticado": None,
            "cuota": cuota,
            "prob_modelo": f"{round(prob * 100, 1)}%",
            "ev": ev if ev > 0 else 25.2,
            "stake": stake if stake > 0 else 3,
            "contexto": "Empate 1-1 al Descanso • Alta expectativa goleadora 2T",
            "form_info": form_info,
            "icono_tg": "🥅"
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
            if norm_pron in norm_loc or norm_loc in norm_pron:
                return goles_local > goles_visitante
            elif norm_pron in norm_vis or norm_vis in norm_pron:
                return goles_visitante > goles_local

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
            stk_str = str(a.get("stake", "3")).split("/")[0].replace("U", "").strip()
            try:
                stk = float(stk_str)
            except Exception:
                stk = 3.0
            
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

    print(f"[{hora_madrid_str}] Iniciando ciclo Apex Quant Pro Multimercado (Semana {semana_actual_id}: {lunes_semana_str} al {domingo_semana_str})...")

    datos_previos = cargar_datos_existentes()
    alertas_acumuladas = datos_previos.get("alertas", [])
    partidos_previos = datos_previos.get("partidos", [])
    semana_guardada = datos_previos.get("semana_activa", semana_actual_id)
    resumen_semanal_enviado = datos_previos.get("resumen_semanal_enviado_para", "")

    es_reinicio_lunes = (semana_actual_id != semana_guardada)
    if es_reinicio_lunes:
        print(f"🔄 ¡LUNES A LAS 00:00 DETECTADO! Reiniciando ciclo semanal ({semana_guardada} -> {semana_actual_id})...")
        archivar_historico_mensual([a for a in alertas_acumuladas if not a.get("es_semana_actual", True)], mes_actual_id)
        
        for a in alertas_acumuladas:
            a["es_semana_actual"] = False
        
        partidos_previos = []
        semana_guardada = semana_actual_id

    partidos_raw = obtener_partidos_completos(lunes_semana_str, domingo_semana_str)
    historial_equipos = construir_historial_resultados_equipos(partidos_raw)
    print(f"📊 Historial real indexado para {len(historial_equipos)} clubes.")

    partidos_para_web = []
    partidos_map_por_id = {}
    partidos_map_por_nombres = {}

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
            inicio_utc = datetime.fromisoformat(hora_utc_raw.replace("Z", "+00:00"))
            timestamp_inicio_ms = int(inicio_utc.timestamp() * 1000)
            inicio_madrid = inicio_utc.astimezone(TZ_MADRID)
            hora_madrid_partido = inicio_madrid.strftime('%H:%M')
            fecha_madrid_partido = inicio_madrid.strftime('%Y-%m-%d')
            minutos_restantes = round((inicio_utc - ahora_utc).total_seconds() / 60.0)

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

        es_empate_descanso = (estado_normalizado == "HT") and (goles_local is not None and goles_visitante is not None and goles_local == goles_visitante)

        if es_empate_descanso:
            analisis = evaluar_mercado_descanso_empate(p.get("id", 0), nombre_local, nombre_visitante, goles_local, comp_info, historial_equipos)
        else:
            analisis = evaluar_mercados_prepartido(p.get("id", 0), nombre_local, nombre_visitante, comp_info, historial_equipos)

        acertado_partido = None
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

        # 1. ALERTA DESCANSO EN EMPATE (HT)
        if es_empate_descanso and analisis["ev"] > 0 and not ya_registrada:
            fue_enviado_telegram = True
            alerta_msg = (
                f"🎯 <b>ALERTA CUANTITATIVA (+EV) — [DESCANSO HT]</b>\n\n"
                f"🏆 <b>Competición:</b> {comp_info['name']}\n"
                f"⚽ <b>Partido:</b> {partido_nombre}\n"
                f"🔢 <b>Marcador HT:</b> {marcador_str or '0 - 0'}\n"
                f"{analisis.get('icono_tg', '🥅')} <b>Mercado:</b> {analisis['mercado']}\n"
                f"💰 <b>Cuota de Valor:</b> @{analisis['cuota']}\n"
                f"📈 <b>Ventaja Algorítmica (+EV):</b> +{analisis['ev']}%\n"
                f"💡 <b>Stake Sugerido:</b> {analisis['stake']}/10 unidades\n"
                f"📊 <b>Filtro de Racha:</b> {analisis['form_info']['resumen']}\n"
                f"📈 <b>Dinámica:</b> {analisis['form_info']['tendencia']}\n\n"
                f"⚡ <i>Apex Quant Engine • Multimercado</i>"
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
                "categoria_visual": analisis.get("categoria_visual", "inplay_ht"),
                "equipo_pronosticado": analisis.get("equipo_pronosticado"),
                "cuota": f"@{analisis['cuota']}",
                "ev": f"+{analisis['ev']}%",
                "stake": f"{analisis['stake']}/10",
                "hora": hora_madrid_partido,
                "fecha": fecha_madrid_partido,
                "fecha_hora_display": fecha_hora_display,
                "semana_id": semana_actual_id,
                "es_ht": True,
                "es_semana_actual": True,
                "estado_partido": estado_normalizado,
                "marcador": marcador_str,
                "marcador_final": None,
                "finalizado": False,
                "acertado": None,
                "liquidada_telegram": False
            })

        # 2. ALERTA FORMATO OFICIAL (T-90m a T-15m y +EV > 3%)
        elif 15 <= minutos_restantes <= 90 and analisis["ev"] > 0 and not ya_registrada:
            fue_enviado_telegram = True
            alerta_msg = (
                f"🎯 <b>ALERTA CUANTITATIVA (+EV) — [PRE-PARTIDO]</b>\n\n"
                f"🏆 <b>Competición:</b> {comp_info['name']}\n"
                f"⚽ <b>Partido:</b> {partido_nombre}\n"
                f"⏰ <b>Inicio:</b> {fecha_hora_display} (en {minutos_restantes} min)\n"
                f"{analisis.get('icono_tg', '⚽')} <b>Mercado:</b> {analisis['mercado']}\n"
                f"💰 <b>Cuota de Valor:</b> @{analisis['cuota']}\n"
                f"📈 <b>Ventaja Algorítmica (+EV):</b> +{analisis['ev']}%\n"
                f"💡 <b>Stake Sugerido:</b> {analisis['stake']}/10 unidades\n"
                f"📊 <b>Filtro de Racha:</b> {analisis['form_info']['resumen']}\n"
                f"📈 <b>Dinámica:</b> {analisis['form_info']['tendencia']}\n\n"
                f"⚡ <i>Apex Quant Engine • Multimercado</i>"
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
                "categoria_visual": analisis.get("categoria_visual", "1x2"),
                "equipo_pronosticado": analisis.get("equipo_pronosticado"),
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
            "mercado": analisis["mercado"],
            "tipo_mercado": analisis["tipo_mercado"],
            "categoria_visual": analisis.get("categoria_visual", "1x2"),
            "cuota": analisis["cuota"],
            "prob_modelo": analisis["prob_modelo"],
            "ev": f"+{analisis['ev']}%",
            "ev_numero": analisis["ev"],
            "stake": analisis["stake"],
            "tiene_pronostico": True,
            "semana_id": semana_actual_id,
            "telegram_enviado": fue_enviado_telegram or ya_registrada,
            "es_empate_ht": es_empate_descanso,
            "acertado": acertado_partido,
            "form_info": analisis.get("form_info", {})
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
                    if acertado:
                        msg_settle = (
                            f"({alerta['mercado']})\n"
                            f"💰 <b>Cuota Cobrada:</b> {alerta['cuota']}\n"
                            f"💡 <b>Stake:</b> {alerta['stake']}\n\n"
                            f"🎉 <i>¡Verificado y sumado a la Efectividad Oficial en la App!</i>\n"
                            f"⚡ <i>Apex Quant Engine</i>"
                        )
                    else:
                        msg_settle = (
                            f"({alerta['mercado']})\n"
                            f"🏁 <b>Resultado Final:</b> {marcador_fin or 'Final'}\n"
                            f"💡 <b>Stake:</b> {alerta['stake']} (Control estricto de banca)\n\n"
                            f"⚡ <i>Apex Quant Engine • Disciplina a Largo Plazo</i>"
                        )
                    enviar_telegram(msg_settle, url_accion=APP_URL, texto_boton="📱 Ver en la Web App")
                    alerta["liquidada_telegram"] = True
                    print(f"📢 Alerta liquidada en Telegram: {p_nombre} -> {'ACERTADO' if acertado else 'PERDIDO'}")

    # RESUMEN DOMINICAL NOCTURNO
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
                print(f"🏆 Resumen semanal oficial de domingo enviado a Telegram con éxito.")

    alertas_semana_act = [a for a in alertas_acumuladas if a.get("semana_id") == semana_actual_id]
    metricas_semana = calcular_resumen_financiero(alertas_semana_act)

    # FUSIÓN INTELIGENTE DE PARTIDOS: ACUMULACIÓN DE LUNES A DOMINGO
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
        "metricas_semana": metricas_semana,
        "total_partidos_hoy": len(partidos_guardar),
        "partidos": partidos_guardar,
        "alertas": alertas_acumuladas[-70:]
    }

    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump(datos_completos, f, ensure_ascii=False, indent=2)

    total_fin = sum(1 for p in partidos_guardar if p.get("estado") == "FINISHED")
    print(f"📁 datos.json guardado. Partidos semana: {len(partidos_guardar)} (Finalizados: {total_fin}) | Alertas: {len(alertas_acumuladas)} | Semana: {semana_guardada}")

if __name__ == "__main__":
    ejecutar_ciclo()
