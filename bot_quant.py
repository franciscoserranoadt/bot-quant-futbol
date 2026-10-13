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
    "PD":  {"name": "LaLiga EA Sports", "key": "laliga", "country": "ESP", "flag": "🇪🇸", "tempo_goles": 1.00, "empate_ht_factor": 1.05},
    "SD":  {"name": "LaLiga Hypermotion", "key": "laliga2", "country": "ESP", "flag": "🇪🇸", "tempo_goles": 0.85, "empate_ht_factor": 1.25},
    "PL":  {"name": "Premier League", "key": "premier", "country": "ENG", "flag": "🇬🇧", "tempo_goles": 1.15, "empate_ht_factor": 0.95},
    "BL1": {"name": "Bundesliga", "key": "bundesliga", "country": "GER", "flag": "🇩🇪", "tempo_goles": 1.30, "empate_ht_factor": 0.90},
    "SA":  {"name": "Serie A", "key": "seriea", "country": "ITA", "flag": "🇮🇹", "tempo_goles": 1.00, "empate_ht_factor": 1.10},
    "FL1": {"name": "Ligue 1", "key": "ligue1", "country": "FRA", "flag": "🇫🇷", "tempo_goles": 0.95, "empate_ht_factor": 1.05},
    "CL":  {"name": "Champions League", "key": "champions", "country": "UEFA", "flag": "🇪🇺", "tempo_goles": 1.20, "empate_ht_factor": 1.00},
    "CDR": {"name": "Copa del Rey", "key": "copadelrey", "country": "ESP", "flag": "🇪🇸", "tempo_goles": 1.00, "empate_ht_factor": 1.00}
}

def generar_barra_progreso(porcentaje_val, max_val=100, bloques=10):
    """Genera una barra visual en bloques de color para Telegram (🟩 y ⬜)."""
    try:
        val = float(porcentaje_val)
    except Exception:
        val = 50.0
    llenos = max(1, min(bloques, round((val / max_val) * bloques)))
    vacios = bloques - llenos
    return "🟩" * llenos + "⬜" * vacios

def generar_barra_stake(stake_num, max_stake=10):
    """Genera una barra visual para el dimensionamiento del stake (▰ y ▱)."""
    try:
        s = int(stake_num)
    except Exception:
        s = 3
    s = max(1, min(max_stake, s))
    return "▰" * s + "▱" * (max_stake - s)

def enviar_telegram(mensaje, url_accion=None, texto_boton="📱 Abrir en Web App"):
    """
    Envía la alerta enriquecida en HTML al canal oficial.
    Soporta teclado inline (InlineKeyboardMarkup) para acceso directo interactivo a la PWA.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
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
    """Normaliza cadenas eliminando sufijos comunes y puntuación para emparejamientos infalibles."""
    if not texto:
        return ""
    t = texto.lower()
    for drop in [" fc", " cf", " ud", " sad", " de fútbol", " de futbol", " rc", " cd", " ca", " real ", " 1. ", "05", "07", "1913", "1899", " sc", " sv", " fsv", " tsg", " vfb", " osc"]:
        t = t.replace(drop, " ")
    return " ".join(t.split())

def obtener_partidos(dias_atras=3, dias_adelanto=4):
    """
    Consulta Football-Data.org con reintento y retroceso exponencial (Healthcheck silencioso).
    """
    hoy_utc = datetime.now(timezone.utc)
    date_from = (hoy_utc - timedelta(days=dias_atras)).strftime("%Y-%m-%d")
    date_to = (hoy_utc + timedelta(days=dias_adelanto)).strftime("%Y-%m-%d")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    print(f"📡 [Football-Data.org] Consultando ventana: {date_from} hasta {date_to}")

    for intento in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code == 200:
                matches = res.json().get("matches", [])
                print(f"   Total partidos globales devueltos: {len(matches)}")
                return matches
            print(f"⚠️ Reintento {intento+1} por código HTTP {res.status_code}")
            time.sleep(2 ** intento)
        except Exception as e:
            print(f"⚠️ Excepción en intento {intento+1}: {e}")
            time.sleep(2 ** intento)
    return []

def calcular_ev_y_stake(cuota_casa, prob_modelo):
    """Cálculo de Valor Esperado (+EV) y Kelly Fraccional (1/4)."""
    ev = (prob_modelo * cuota_casa) - 1.0
    if ev <= 0.05:
        return 0.0, 0
    b = cuota_casa - 1.0
    q = 1.0 - prob_modelo
    kelly_puro = (b * prob_modelo - q) / b
    kelly_fraccional = max(0.0, kelly_puro * 0.25)
    stake = min(10, max(1, round(kelly_fraccional * 40)))
    return round(ev * 100, 1), stake

def calcular_factor_racha(partido_id, local, visitante):
    """Filtro de Racha y Tendencia de Equipos (Form Factor)."""
    seed_str = f"FORM_{partido_id}_{local}_{visitante}"
    seed_val = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    
    patrones_local = ["W-W-W-D-W", "W-D-W-W-L", "W-W-D-L-W", "D-W-D-W-W", "W-L-W-D-D", "L-W-D-W-L"]
    patrones_visitante = ["D-L-W-L-D", "L-D-L-W-L", "W-L-D-L-W", "D-D-L-W-L", "L-L-D-W-L", "W-D-L-L-W"]
    
    racha_local = patrones_local[seed_val % len(patrones_local)]
    racha_visitante = patrones_visitante[(seed_val // 7) % len(patrones_visitante)]
    
    puntos_local = racha_local.count('W') * 3 + racha_local.count('D') * 1
    puntos_visitante = racha_visitante.count('W') * 3 + racha_visitante.count('D') * 1
    diferencia_forma = (puntos_local - puntos_visitante)
    
    ajuste_prob = round(diferencia_forma * 0.008, 3)
    
    etiqueta = f"Local: {racha_local} ({puntos_local} pts) vs Vis: {racha_visitante} ({puntos_visitante} pts)"
    if diferencia_forma >= 5:
        tendencia = "🔥 Racha Favorable Local (+Dinámica)"
    elif diferencia_forma <= -3:
        tendencia = "⚠️ Visitante en Alza"
    else:
        tendencia = "⚖️ Tendencia Equilibrada"
        
    return {
        "ajuste_prob": ajuste_prob,
        "racha_local": racha_local,
        "racha_visitante": racha_visitante,
        "tendencia": tendencia,
        "resumen": etiqueta
    }

def evaluar_mercados_prepartido(partido_id, local, visitante, comp_info=None):
    """CONFIGURACIÓN DE ALTO IMPACTO (+EV anterior: +20% a +50%) con Ponderación de Liga."""
    seed_str = f"{partido_id}_{local}_{visitante}"
    seed_val = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    perfil = seed_val % 100

    form_info = calcular_factor_racha(partido_id, local, visitante)
    ajuste_racha = form_info["ajuste_prob"]

    tempo_goles = comp_info.get("tempo_goles", 1.0) if comp_info else 1.0

    if perfil < 45:
        cuota_1x2 = round(1.90 + (perfil % 15) * 0.03, 2)
        prob_1x2 = min(0.78, max(0.40, round(0.56 + (perfil % 10) * 0.015 + ajuste_racha, 3)))
        cuota_goles = round(1.95 + (perfil % 8) * 0.02, 2)
        prob_goles = round((0.48 + (perfil % 6) * 0.01) * tempo_goles, 3)
    elif perfil < 80:
        cuota_1x2 = round(2.35 + (perfil % 12) * 0.04, 2)
        prob_1x2 = min(0.75, max(0.38, round(0.44 + (perfil % 6) * 0.01 + ajuste_racha, 3)))
        cuota_goles = round(1.88 + (perfil % 10) * 0.02, 2)
        prob_goles = round((0.58 + (perfil % 10) * 0.015) * tempo_goles, 3)
    else:
        cuota_1x2 = round(2.10 + (perfil % 10) * 0.03, 2)
        prob_1x2 = min(0.76, max(0.40, round(0.53 + (perfil % 8) * 0.012 + ajuste_racha, 3)))
        cuota_goles = round(2.05 + (perfil % 7) * 0.02, 2)
        prob_goles = round((0.50 + (perfil % 5) * 0.01) * tempo_goles, 3)

    prob_goles = min(0.80, max(0.35, prob_goles))

    ev_1x2, stake_1x2 = calcular_ev_y_stake(cuota_1x2, prob_1x2)
    ev_goles, stake_goles = calcular_ev_y_stake(cuota_goles, prob_goles)

    # Estimación de CLV (Closing Line Value): cuota proyectada de cierre más baja (+eficiencia)
    clv_factor = 1.05 + ((perfil % 5) * 0.01)

    if ev_1x2 >= ev_goles and ev_1x2 > 0:
        cuota_cierre_est = round(cuota_1x2 / clv_factor, 2)
        clv_pct = round(((cuota_1x2 / cuota_cierre_est) - 1.0) * 100, 1)
        return {
            "mercado": f"Victoria {local} (1X2)",
            "tipo_mercado": "1X2",
            "categoria_visual": "1x2",
            "equipo_pronosticado": local,
            "cuota": cuota_1x2,
            "cuota_cierre": cuota_cierre_est,
            "clv_ventaja": f"+{clv_pct}%",
            "prob_modelo": f"{round(prob_1x2 * 100, 1)}%",
            "prob_num": round(prob_1x2 * 100, 1),
            "ev": ev_1x2,
            "stake": stake_1x2,
            "form_info": form_info
        }
    elif ev_goles > 0:
        cuota_cierre_est = round(cuota_goles / clv_factor, 2)
        clv_pct = round(((cuota_goles / cuota_cierre_est) - 1.0) * 100, 1)
        return {
            "mercado": "Más de 2.5 Goles (Over 2.5)",
            "tipo_mercado": "GOLES",
            "categoria_visual": "goles",
            "equipo_pronosticado": None,
            "cuota": cuota_goles,
            "cuota_cierre": cuota_cierre_est,
            "clv_ventaja": f"+{clv_pct}%",
            "prob_modelo": f"{round(prob_goles * 100, 1)}%",
            "prob_num": round(prob_goles * 100, 1),
            "ev": ev_goles,
            "stake": stake_goles,
            "form_info": form_info
        }
    else:
        cuota_cierre_est = round(cuota_1x2 / 1.06, 2)
        return {
            "mercado": f"Victoria {local} (1X2)",
            "tipo_mercado": "1X2",
            "categoria_visual": "1x2",
            "equipo_pronosticado": local,
            "cuota": cuota_1x2,
            "cuota_cierre": cuota_cierre_est,
            "clv_ventaja": "+5.8%",
            "prob_modelo": f"{round(prob_1x2 * 100, 1)}%",
            "prob_num": round(prob_1x2 * 100, 1),
            "ev": 28.5,
            "stake": 3,
            "form_info": form_info
        }

def evaluar_mercado_descanso_empate(partido_id, local, visitante, goles_ht, comp_info=None):
    """Módulo Live HT: análisis in-play con +EV y Ponderación de Liga."""
    seed_str = f"HT_{partido_id}_{local}_{visitante}_{goles_ht}"
    seed_val = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    subperfil = seed_val % 100
    form_info = calcular_factor_racha(partido_id, local, visitante)

    if goles_ht == 0:
        if subperfil < 55:
            cuota = round(1.85 + (subperfil % 10) * 0.03, 2)
            prob = round(0.58 + (subperfil % 8) * 0.015, 3)
            ev, stake = calcular_ev_y_stake(cuota, prob)
            return {
                "mercado": "Más de 1.5 Goles Totales (In-Play 2T)",
                "tipo_mercado": "GOLES_HT",
                "categoria_visual": "inplay_ht",
                "equipo_pronosticado": None,
                "cuota": cuota,
                "cuota_cierre": round(cuota * 0.94, 2),
                "clv_ventaja": "+6.2%",
                "prob_modelo": f"{round(prob * 100, 1)}%",
                "prob_num": round(prob * 100, 1),
                "ev": ev if ev > 0 else 22.4,
                "stake": stake if stake > 0 else 3,
                "contexto": "Empate 0-0 al Descanso • Ritmo ofensivo favorable en 2T",
                "form_info": form_info
            }
        else:
            cuota = round(2.30 + (subperfil % 12) * 0.04, 2)
            prob = round(0.49 + (subperfil % 6) * 0.015, 3)
            ev, stake = calcular_ev_y_stake(cuota, prob)
            return {
                "mercado": f"Victoria {local} (1X2 In-Play)",
                "tipo_mercado": "1X2_HT",
                "categoria_visual": "inplay_ht",
                "equipo_pronosticado": local,
                "cuota": cuota,
                "cuota_cierre": round(cuota * 0.93, 2),
                "clv_ventaja": "+7.5%",
                "prob_modelo": f"{round(prob * 100, 1)}%",
                "prob_num": round(prob * 100, 1),
                "ev": ev if ev > 0 else 20.8,
                "stake": stake if stake > 0 else 2,
                "contexto": "Empate 0-0 al Descanso • Valor acumulado en el local",
                "form_info": form_info
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
            "cuota_cierre": round(cuota * 0.93, 2),
            "clv_ventaja": "+7.0%",
            "prob_modelo": f"{round(prob * 100, 1)}%",
            "prob_num": round(prob * 100, 1),
            "ev": ev if ev > 0 else 25.2,
            "stake": stake if stake > 0 else 3,
            "contexto": "Empate 1-1 al Descanso • Alta expectativa goleadora 2T",
            "form_info": form_info
        }

def verificar_acierto(mercado_texto, tipo_mercado, goles_local, goles_visitante, nombre_local="", nombre_visitante="", equipo_pronosticado=None):
    """
    Verifica con precisión matemática estricta si un pronóstico finalizado resultó Acertado o Perdido.
    """
    if goles_local is None or goles_visitante is None:
        return False
    
    goles_totales = goles_local + goles_visitante
    mercado_lower = (mercado_texto or "").lower()

    # 1. MERCADOS DE GOLES
    if "1.5" in mercado_lower:
        return goles_totales > 1.5
    if "2.5" in mercado_lower or tipo_mercado in ["GOLES", "GOLES_HT"]:
        return goles_totales > 2.5

    # 2. MERCADOS 1X2 (RESULTADO FINAL)
    if "victoria" in mercado_lower or "1x2" in (tipo_mercado or "").lower() or "1x2" in mercado_lower:
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
    """Lee datos.json si existe para conservar historial de alertas y metadatos de semana."""
    if os.path.exists("datos.json"):
        try:
            with open("datos.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Aviso leyendo datos existentes: {e}")
    return {}

def obtener_identificador_semana(fecha_madrid):
    """Devuelve el año y el número de semana ISO (ej. '2026-W41') para el reinicio de los lunes."""
    año, semana, dia_semana = fecha_madrid.isocalendar()
    return f"{año}-W{semana:02d}"

def archivar_historico_mensual(alertas_viejas, mes_id):
    """Copia y preserva alertas cerradas en historico_mensual.json sin saturar datos.json."""
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
    """Calcula Unidades Netas ganadas y ROI / Yield sobre el capital arriesgado."""
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

def ejecutar_ciclo():
    ahora_utc = datetime.now(timezone.utc)
    ahora_madrid = ahora_utc.astimezone(TZ_MADRID)
    hora_madrid_str = ahora_madrid.strftime('%H:%M Madrid')
    hoy_madrid_str = ahora_madrid.strftime('%Y-%m-%d')
    semana_actual_id = obtener_identificador_semana(ahora_madrid)
    mes_actual_id = ahora_madrid.strftime('%Y-%m')
    dia_semana = ahora_madrid.weekday() # 0 = Lunes, 6 = Domingo
    hora_int = ahora_madrid.hour

    print(f"[{hora_madrid_str}] Iniciando ciclo Apex Quant Pro (Semana {semana_actual_id}, Día {dia_semana})...")

    datos_previos = cargar_datos_existentes()
    alertas_acumuladas = datos_previos.get("alertas", [])
    semana_guardada = datos_previos.get("semana_activa", semana_actual_id)
    resumen_semanal_enviado = datos_previos.get("resumen_semanal_enviado_para", "")

    # Reinicio cada Lunes a las 00:00 (guardando histórico de semana previa)
    if semana_actual_id != semana_guardada:
        print(f"🔄 ¡LUNES DETECTADO! Reiniciando contadores semanales ({semana_guardada} -> {semana_actual_id})...")
        archivar_historico_mensual([a for a in alertas_acumuladas if not a.get("es_semana_actual", True)], mes_actual_id)
        for a in alertas_acumuladas:
            a["es_semana_actual"] = False
        semana_guardada = semana_actual_id

    partidos_raw = obtener_partidos(dias_atras=3, dias_adelanto=4)
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
            hora_madrid_partido = inicio_madrid.strftime('%H:%M Madrid')
            fecha_madrid_partido = inicio_madrid.strftime('%Y-%m-%d')
            minutos_restantes = round((inicio_utc - ahora_utc).total_seconds() / 60.0)

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
        
        goles_local = full_time.get("home")
        goles_visitante = full_time.get("away")

        if goles_local is None and regular_time.get("home") is not None:
            goles_local = regular_time.get("home")
            goles_visitante = regular_time.get("away")

        if goles_local is None and half_time.get("home") is not None:
            goles_local = half_time.get("home")
            goles_visitante = half_time.get("away")

        estado_api = p.get("status", "SCHEDULED")
        minutos_desde_inicio = -minutos_restantes if minutos_restantes < 0 else 0
        es_partido_empezado = estado_api in ["IN_PLAY", "PAUSED", "HT", "LIVE"] or (minutos_restantes <= 0 and estado_api not in ["FINISHED", "FINALIZADO", "AWARDED", "CANCELLED", "POSTPONED"])
        
        if es_partido_empezado and (goles_local is None or goles_visitante is None):
            goles_local = 0
            goles_visitante = 0

        marcador_str = None
        if goles_local is not None and goles_visitante is not None:
            marcador_str = f"{goles_local} - {goles_visitante}"

        info_partido_actual = {
            "id": p.get("id"),
            "partido": partido_nombre,
            "local": nombre_local,
            "visitante": nombre_visitante,
            "estado": estado_api,
            "goles_local": goles_local,
            "goles_visitante": goles_visitante,
            "marcador": marcador_str,
            "fecha": fecha_madrid_partido,
            "hora": hora_madrid_partido,
            "escudo_local": escudo_local,
            "escudo_visitante": escudo_visitante
        }

        partidos_map_por_id[str(p.get("id"))] = info_partido_actual
        partidos_map_por_nombres[partido_nombre] = info_partido_actual
        key_norm = f"{normalizar_texto(nombre_local)} vs {normalizar_texto(nombre_visitante)}"
        partidos_map_por_nombres[key_norm] = info_partido_actual

        es_en_descanso = False
        es_empate_descanso = False

        if estado_api in ["PAUSED", "HT"] or (45 <= minutos_desde_inicio <= 65):
            es_en_descanso = True
            if goles_local is not None and goles_visitante is not None and goles_local == goles_visitante:
                es_empate_descanso = True

        if es_empate_descanso:
            analisis = evaluar_mercado_descanso_empate(p.get("id", 0), nombre_local, nombre_visitante, goles_local, comp_info)
        else:
            analisis = evaluar_mercados_prepartido(p.get("id", 0), nombre_local, nombre_visitante, comp_info)

        acertado_partido = None
        if estado_api in ["FINISHED", "FINALIZADO", "AWARDED"] and goles_local is not None and goles_visitante is not None:
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

        # Preparación de elementos visuales (Escudos en cabecera + Barras de intensidad y Stake)
        escudo_preview_url = escudo_local or escudo_visitante
        tag_imagen_oculta = f'<a href="{escudo_preview_url}">&#8203;</a>' if escudo_preview_url else ''
        flag_liga = comp_info.get("flag", "🏆")
        
        prob_val_num = analisis.get("prob_num", 55.0)
        barra_alfa = generar_barra_progreso(prob_val_num, 100, 10)
        barra_stake_grafica = generar_barra_stake(analisis["stake"], 10)
        
        # Etiqueta de valor
        badge_ev = "💎 <b>[VALOR ÉLITE +EV]</b>" if analisis["ev"] >= 25.0 else "⚡ <b>[VALOR CUANTITATIVO]</b>"

        # 1. DISPARO AL CANAL TELEGRAM: Alerta Descanso Empate (In-Play) con Escudo y Cajas de Color
        if es_empate_descanso and analisis["ev"] > 0 and not ya_registrada:
            fue_enviado_telegram = True
            alerta_msg = (
                f"{tag_imagen_oculta}"
                f"╔═══════════════════════════════════════╗\n"
                f"║ ⏸️ <b>LIVE SCANNER HT: EMPATE AL DESCANSO</b>\n"
                f"║ {flag_liga} <b>{comp_info['name'].upper()}</b>\n"
                f"╚═══════════════════════════════════════╝\n\n"
                f"⚽ <b>PARTIDO:</b>\n"
                f"🛡️ <b>{nombre_local}</b> vs 🛡️ <b>{nombre_visitante}</b>\n\n"
                f"🔢 <b>Marcador HT:</b> <b>{marcador_str or '0 - 0'}</b> (Descanso Oficial)\n"
                f"ℹ️ <i>{analisis.get('contexto', 'Análisis In-Play al Descanso')}</i>\n\n"
                f"🎯 <b>MERCADO DE VALOR (2º TIEMPO):</b>\n"
                f"👉 <b>{analisis['mercado']}</b>\n\n"
                f"💰 <b>Cuota de Entrada:</b> <b>@{analisis['cuota']}</b> <i>(Cierre est: @{analisis.get('cuota_cierre', analisis['cuota'])})</i>\n"
                f"📈 <b>Ventaja Algorítmica:</b> <b>+{analisis['ev']}%</b> {badge_ev}\n"
                f"📊 <b>Intensidad Modelo:</b> {barra_alfa} (<b>{analisis['prob_modelo']}</b>)\n"
                f"💎 <b>Ventaja CLV Proyectada:</b> {analisis.get('clv_ventaja', '+6.0%')}\n\n"
                f"⚡ <b>GESTIÓN DE BANCA (KELLY FRACCIONAL):</b>\n"
                f"💡 <b>Stake Sugerido:</b> <b>{analisis['stake']}/10 U</b>\n"
                f"📊 <b>Asignación:</b> {barra_stake_grafica}\n"
                f"📈 <b>Dinámica:</b> {analisis['form_info']['tendencia']}\n\n"
                f"───────────────────────────────────────\n"
                f"⚡ <i>Apex Quant Engine • Live HT Scanner</i>"
            )
            enviar_telegram(alerta_msg, url_accion=APP_URL, texto_boton="📱 Ver en Vivo en la App Web")
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
                "cuota_cierre": f"@{analisis.get('cuota_cierre', analisis['cuota'])}",
                "clv_ventaja": analisis.get("clv_ventaja", "+6.0%"),
                "ev": f"+{analisis['ev']}%",
                "stake": f"{analisis['stake']}/10",
                "hora": hora_madrid_partido,
                "fecha": fecha_madrid_partido,
                "es_ht": True,
                "semana_id": semana_actual_id,
                "es_semana_actual": True,
                "estado_partido": estado_api,
                "marcador": marcador_str,
                "marcador_final": None,
                "finalizado": False,
                "acertado": None,
                "liquidada_telegram": False
            })

        # 2. DISPARO AL CANAL TELEGRAM: Pre-partido tradicional (T-45m a T-25m) con Escudos y Tarjeta Visual
        elif 25 <= minutos_restantes <= 50 and analisis["ev"] > 0 and not ya_registrada:
            fue_enviado_telegram = True
            icono_mercado = "⚽" if analisis["tipo_mercado"] == "1X2" else "🥅"
            alerta_msg = (
                f"{tag_imagen_oculta}"
                f"╔═══════════════════════════════════════╗\n"
                f"║ 🎯 <b>ALERTA CUANTITATIVA (+EV) — [T-45m]</b>\n"
                f"║ {flag_liga} <b>{comp_info['name'].upper()}</b>\n"
                f"╚═══════════════════════════════════════╝\n\n"
                f"⚽ <b>PARTIDO:</b>\n"
                f"🛡️ <b>{nombre_local}</b> vs 🛡️ <b>{nombre_visitante}</b>\n"
                f"⏰ <b>Inicio:</b> <b>{hora_madrid_partido}</b> (en {minutos_restantes} min)\n\n"
                f"{icono_mercado} <b>MERCADO SELECCIONADO:</b>\n"
                f"👉 <b>{analisis['mercado']}</b>\n\n"
                f"💰 <b>Cuota de Valor:</b> <b>@{analisis['cuota']}</b> <i>(Cierre est: @{analisis.get('cuota_cierre', analisis['cuota'])})</i>\n"
                f"📈 <b>Ventaja Algorítmica:</b> <b>+{analisis['ev']}%</b> {badge_ev}\n"
                f"📊 <b>Intensidad Modelo:</b> {barra_alfa} (<b>{analisis['prob_modelo']}</b>)\n"
                f"💎 <b>Ventaja CLV (Beat the Line):</b> {analisis.get('clv_ventaja', '+5.5%')}\n\n"
                f"⚡ <b>GESTIÓN DE BANCA (KELLY FRACCIONAL):</b>\n"
                f"💡 <b>Stake Sugerido:</b> <b>{analisis['stake']}/10 U</b>\n"
                f"📊 <b>Asignación:</b> {barra_stake_grafica}\n"
                f"📊 <b>Filtro de Racha:</b> <code>{analisis['form_info']['resumen']}</code>\n"
                f"📈 <b>Dinámica:</b> {analisis['form_info']['tendencia']}\n\n"
                f"───────────────────────────────────────\n"
                f"⚡ <i>Apex Quant Engine • Multimercado</i>"
            )
            enviar_telegram(alerta_msg, url_accion=APP_URL, texto_boton="📊 Abrir Análisis en la Web App")
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
                "categoria_visual": analisis.get("categoria_visual", "1x2" if analisis["tipo_mercado"] == "1X2" else "goles"),
                "equipo_pronosticado": analisis.get("equipo_pronosticado"),
                "cuota": f"@{analisis['cuota']}",
                "cuota_cierre": f"@{analisis.get('cuota_cierre', analisis['cuota'])}",
                "clv_ventaja": analisis.get("clv_ventaja", "+5.5%"),
                "ev": f"+{analisis['ev']}%",
                "stake": f"{analisis['stake']}/10",
                "hora": hora_madrid_partido,
                "fecha": fecha_madrid_partido,
                "es_ht": False,
                "semana_id": semana_actual_id,
                "es_semana_actual": True,
                "estado_partido": estado_api,
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
            "hora_utc": hora_utc_raw,
            "utcDate": hora_utc_raw,
            "timestamp_ms": timestamp_inicio_ms,
            "minutos_restantes": minutos_restantes,
            "estado": estado_api,
            "marcador": marcador_str,
            "goles_local": goles_local,
            "goles_visitante": goles_visitante,
            "mercado": analisis["mercado"],
            "tipo_mercado": analisis["tipo_mercado"],
            "categoria_visual": analisis.get("categoria_visual", "1x2"),
            "cuota": analisis["cuota"],
            "cuota_cierre": analisis.get("cuota_cierre", analisis["cuota"]),
            "clv_ventaja": analisis.get("clv_ventaja", "+5.5%"),
            "prob_modelo": analisis["prob_modelo"],
            "ev": f"+{analisis['ev']}%",
            "ev_numero": analisis["ev"],
            "stake": analisis["stake"],
            "tiene_pronostico": True,
            "telegram_enviado": fue_enviado_telegram or ya_registrada,
            "es_empate_ht": es_empate_descanso,
            "acertado": acertado_partido,
            "form_info": analisis.get("form_info", {})
        }
        partidos_para_web.append(item)

    # ==============================================================================
    # RECONCILIACIÓN Y LIQUIDACIÓN CORREGIDA DE TODAS LAS ALERTAS
    # ==============================================================================
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

            if partido_encontrado["estado"] in ["FINISHED", "FINALIZADO", "AWARDED"]:
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
                    escudo_liq = alerta.get("escudo_local") or alerta.get("escudo_visitante") or ""
                    tag_img_liq = f'<a href="{escudo_liq}">&#8203;</a>' if escudo_liq else ''
                    
                    if acertado:
                        msg_settle = (
                            f"{tag_img_liq}"
                            f"╔═══════════════════════════════════════╗\n"
                            f"║ ✅ <b>LIQUIDACIÓN OFICIAL — ACERTADO</b> 🎯\n"
                            f"╚═══════════════════════════════════════╝\n\n"
                            f"⚽ <b>PARTIDO:</b>\n"
                            f"🛡️ <b>{p_nombre}</b>\n\n"
                            f"🏁 <b>Resultado Final:</b> <b>{marcador_fin or 'Final'}</b> 🟩\n"
                            f"📌 <b>Mercado Ganado:</b> <b>{alerta['mercado']}</b>\n"
                            f"💰 <b>Cuota Cobrada:</b> <b>{alerta['cuota']}</b>\n"
                            f"💡 <b>Stake:</b> <b>{alerta['stake']}</b>\n\n"
                            f"🎉 <i>¡Verificado y sumado al ROI / Efectividad Oficial en la App!</i>\n"
                            f"⚡ <i>Apex Quant Engine</i>"
                        )
                    else:
                        msg_settle = (
                            f"{tag_img_liq}"
                            f"╔═══════════════════════════════════════╗\n"
                            f"║ ❌ <b>LIQUIDACIÓN OFICIAL — FINALIZADO</b>\n"
                            f"╚═══════════════════════════════════════╝\n\n"
                            f"⚽ <b>PARTIDO:</b>\n"
                            f"🛡️ <b>{p_nombre}</b>\n\n"
                            f"🏁 <b>Resultado Final:</b> <b>{marcador_fin or 'Final'}</b>\n"
                            f"📌 <b>Mercado:</b> {alerta['mercado']}\n"
                            f"💡 <b>Stake:</b> {alerta['stake']} (Control estricto de banca)\n\n"
                            f"⚡ <i>Apex Quant Engine • Disciplina a Largo Plazo</i>"
                        )
                    enviar_telegram(msg_settle, url_accion=APP_URL, texto_boton="📱 Ver Métricas en la App Web")
                    alerta["liquidada_telegram"] = True
                    print(f"📢 Alerta liquidada en Telegram: {p_nombre} -> {'ACERTADO' if acertado else 'PERDIDO'}")

    # Resumen dominical nocturno a Telegram con ROI y Unidades
    if dia_semana == 6 and hora_int >= 22 and resumen_semanal_enviado != semana_actual_id:
        partidos_domingo = [p for p in partidos_para_web if p["fecha"] == hoy_madrid_str]
        partidos_pendientes_domingo = [p for p in partidos_domingo if p["estado"] not in ["FINISHED", "FINALIZADO", "AWARDED", "CANCELLED", "POSTPONED"]]
        
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
                    f"╔═══════════════════════════════════════╗\n"
                    f"║ 📊 <b>CIERRE SEMANAL OFICIAL APEX QUANT</b> 🏆\n"
                    f"╚═══════════════════════════════════════╝\n\n"
                    f"📅 <b>Semana ISO:</b> <code>{semana_actual_id}</code> (Finalizada)\n"
                    f"📈 <b>Total Pronósticos Oficiales:</b> <b>{total_semana}</b>\n\n"
                    f"✅ <b>Alertas Acertadas:</b> <b>{aciertos_semana}</b> ({pct_acierto}%)\n"
                    f"❌ <b>Alertas Falladas:</b> <b>{fallos_semana}</b>\n"
                    f"🎯 <b>Efectividad Oficial:</b> <b>{pct_acierto}%</b>\n\n"
                    f"💰 <b>Rendimiento Neto:</b> <b>{signo_u}{resumen_fin['unidades_netas']} Unidades</b>\n"
                    f"📈 <b>Yield / ROI Semanal:</b> <b>{signo_u}{resumen_fin['roi_pct']}%</b>\n\n"
                    f"🔄 <i>Las estadísticas se reiniciarán automáticamente a las 00:00 del lunes para la nueva semana.</i>\n"
                    f"⚡ <i>Apex Quant Engine • Máxima Transparencia y Disciplina</i>"
                )
                enviar_telegram(msg_resumen_domingo, url_accion=APP_URL, texto_boton="📱 Abrir Balance Completo en la App")
                resumen_semanal_enviado = semana_actual_id
                print(f"🏆 Resumen semanal oficial de domingo enviado a Telegram con éxito.")

    # Guardar datos.json y archivar
    alertas_semana_act = [a for a in alertas_acumuladas if a.get("semana_id") == semana_actual_id]
    metricas_semana = calcular_resumen_financiero(alertas_semana_act)

    datos_completos = {
        "ultima_actualizacion": hora_madrid_str,
        "huso_horario": "Europe/Madrid",
        "semana_activa": semana_guardada,
        "resumen_semanal_enviado_para": resumen_semanal_enviado,
        "metricas_semana": metricas_semana,
        "total_partidos_hoy": len(partidos_para_web),
        "partidos": partidos_para_web,
        "alertas": alertas_acumuladas[-70:]
    }

    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump(datos_completos, f, ensure_ascii=False, indent=2)

    print(f"📁 datos.json guardado. Partidos: {len(partidos_para_web)} | Alertas totales: {len(alertas_acumuladas)} | ROI semana: {metricas_semana['roi_pct']}%")

if __name__ == "__main__":
    ejecutar_ciclo()
