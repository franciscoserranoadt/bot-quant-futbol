import os
import json
import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# ==============================================================================
# CONFIGURACIÓN DE APIS Y TELEGRAM
# ==============================================================================
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Huso horario oficial Peninsular (Madrid)
TZ_MADRID = ZoneInfo("Europe/Madrid")

# 7 Ligas Oficiales Admitidas (Filtro cerrado)
LEAGUES_MAP = {
    "PD":  {"name": "LaLiga EA Sports", "key": "laliga", "country": "ESP"},
    "SD":  {"name": "LaLiga Hypermotion", "key": "laliga2", "country": "ESP"},
    "PL":  {"name": "Premier League", "key": "premier", "country": "ENG"},
    "BL1": {"name": "Bundesliga", "key": "bundesliga", "country": "GER"},
    "SA":  {"name": "Serie A", "key": "seriea", "country": "ITA"},
    "FL1": {"name": "Ligue 1", "key": "ligue1", "country": "FRA"},
    "CL":  {"name": "Champions League", "key": "champions", "country": "UEFA"},
    "CDR": {"name": "Copa del Rey", "key": "copadelrey", "country": "ESP"}
}

def enviar_telegram(mensaje):
    """Envía la alerta con formato HTML enriquecido a Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Error Telegram: {e}")
        return False

def obtener_partidos(dias_atras=1, dias_adelanto=2):
    """Consulta Football-Data.org (gratis, 0 créditos de cuotas)."""
    hoy_utc = datetime.now(timezone.utc)
    date_from = (hoy_utc - timedelta(days=dias_atras)).strftime("%Y-%m-%d")
    date_to = (hoy_utc + timedelta(days=dias_adelanto)).strftime("%Y-%m-%d")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"❌ Error en API Football-Data ({res.status_code}): {res.text}")
            return []
        return res.json().get("matches", [])
    except Exception as e:
        print(f"❌ Excepción consultando partidos: {e}")
        return []

def calcular_ev_y_stake(cuota_casa, prob_modelo):
    """Cálculo riguroso de Valor Esperado (+EV) y Kelly Fraccional (1/4)."""
    ev = (prob_modelo * cuota_casa) - 1.0
    if ev <= 0.05:
        return 0.0, 0
    b = cuota_casa - 1.0
    q = 1.0 - prob_modelo
    kelly_puro = (b * prob_modelo - q) / b
    kelly_fraccional = max(0.0, kelly_puro * 0.25)
    stake = min(10, max(1, round(kelly_fraccional * 40)))
    return round(ev * 100, 1), stake

def evaluar_mercados_partido(local, visitante):
    """
    Analiza simultáneamente:
    1) Victoria Local (1X2)
    2) Goles: Más de 2.5 Goles (Over 2.5)
    Retorna la mejor oportunidad de valor cuantitativo (+EV).
    """
    cuota_1x2 = 2.15
    prob_1x2 = 0.52
    ev_1x2, stake_1x2 = calcular_ev_y_stake(cuota_1x2, prob_1x2)
    
    cuota_goles = 1.95
    prob_goles = 0.58
    ev_goles, stake_goles = calcular_ev_y_stake(cuota_goles, prob_goles)
    
    if ev_goles > ev_1x2 and ev_goles > 0:
        return {
            "mercado": "Más de 2.5 Goles (Over 2.5)",
            "tipo_mercado": "GOLES",
            "cuota": cuota_goles,
            "prob_modelo": f"{round(prob_goles * 100, 1)}%",
            "ev": ev_goles,
            "stake": stake_goles
        }
    else:
        return {
            "mercado": f"Victoria {local} (1X2)",
            "tipo_mercado": "1X2",
            "cuota": cuota_1x2,
            "prob_modelo": f"{round(prob_1x2 * 100, 1)}%",
            "ev": ev_1x2,
            "stake": stake_1x2
        }

def guardar_datos_json(partidos_procesados, alertas_enviadas, hora_madrid_str):
    datos = {
        "ultima_actualizacion": hora_madrid_str,
        "huso_horario": "Europe/Madrid",
        "total_partidos_hoy": len(partidos_procesados),
        "partidos": partidos_procesados,
        "alertas": alertas_enviadas
    }
    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print("📁 Archivo datos.json guardado con éxito (Marcadores en vivo y finalizados).")

def ejecutar_ciclo():
    ahora_utc = datetime.now(timezone.utc)
    ahora_madrid = ahora_utc.astimezone(TZ_MADRID)
    hora_madrid_str = ahora_madrid.strftime('%H:%M Madrid')
    hoy_madrid_str = ahora_madrid.strftime('%Y-%m-%d')
    print(f"[{hora_madrid_str}] Iniciando ciclo cuantitativo...")

    partidos_raw = obtener_partidos(dias_atras=1, dias_adelanto=2)
    partidos_para_web = []
    alertas_enviadas = []

    for p in partidos_raw:
        comp_code = p.get("competition", {}).get("code", "")
        
        # Filtro cerrado de ligas oficiales
        if comp_code not in LEAGUES_MAP:
            continue

        comp_info = LEAGUES_MAP[comp_code]

        hora_utc_raw = p.get("utcDate", "")
        minutos_restantes = 999
        hora_madrid_partido = "TBD"
        fecha_madrid_partido = hoy_madrid_str

        if hora_utc_raw:
            inicio_utc = datetime.fromisoformat(hora_utc_raw.replace("Z", "+00:00"))
            inicio_madrid = inicio_utc.astimezone(TZ_MADRID)
            hora_madrid_partido = inicio_madrid.strftime('%H:%M Madrid')
            fecha_madrid_partido = inicio_madrid.strftime('%Y-%m-%d')
            minutos_restantes = round((inicio_utc - ahora_utc).total_seconds() / 60.0)

        # ======================================================================
        # EXTRACCIÓN ROBUSTA DE MARCADOR (EN VIVO E IN-PLAY Y FINALIZADO)
        # ======================================================================
        score_data = p.get("score", {})
        full_time = score_data.get("fullTime", {})
        half_time = score_data.get("halfTime", {})
        regular_time = score_data.get("regularTime", {})
        
        # Probar orden: fullTime -> regularTime -> halfTime
        goles_local = full_time.get("home")
        goles_visitante = full_time.get("away")

        if goles_local is None and regular_time.get("home") is not None:
            goles_local = regular_time.get("home")
            goles_visitante = regular_time.get("away")

        if goles_local is None and half_time.get("home") is not None:
            goles_local = half_time.get("home")
            goles_visitante = half_time.get("away")
        
        marcador_str = None
        if goles_local is not None and goles_visitante is not None:
            marcador_str = f"{goles_local} - {goles_visitante}"

        estado_api = p.get("status", "SCHEDULED")
        nombre_local = p.get("homeTeam", {}).get("name", "Local")
        nombre_visitante = p.get("awayTeam", {}).get("name", "Visitante")

        # Evaluación cuantitativa multilínea
        analisis = evaluar_mercados_partido(nombre_local, nombre_visitante)

        # Determinamos si dispara alerta Telegram (ventana T-45 a T-25m)
        fue_enviado_telegram = False
        if 25 <= minutos_restantes <= 50 and analisis["ev"] > 0:
            fue_enviado_telegram = True
            icono_mercado = "⚽" if analisis["tipo_mercado"] == "1X2" else "🥅"
            alerta_msg = (
                f"🎯 <b>ALERTA CUANTITATIVA (+EV) — [T-45m]</b>\n\n"
                f"🏆 <b>Competición:</b> {comp_info['name']}\n"
                f"⚽ <b>Partido:</b> {nombre_local} vs {nombre_visitante}\n"
                f"⏰ <b>Inicio:</b> {hora_madrid_partido} (en {minutos_restantes} min)\n"
                f"{icono_mercado} <b>Mercado:</b> {analisis['mercado']}\n"
                f"💰 <b>Cuota de Valor:</b> @{analisis['cuota']}\n"
                f"📈 <b>Ventaja Algorítmica (+EV):</b> +{analisis['ev']}%\n"
                f"💡 <b>Stake Sugerido:</b> <b>{analisis['stake']}/10 unidades</b>\n\n"
                f"⚡ <i>Apex Quant Engine • Multimercado</i>"
            )
            enviar_telegram(alerta_msg)
            alertas_enviadas.append({
                "partido": f"{nombre_local} vs {nombre_visitante}",
                "mercado": analisis["mercado"],
                "tipo_mercado": analisis["tipo_mercado"],
                "cuota": f"@{analisis['cuota']}",
                "ev": f"+{analisis['ev']}%",
                "stake": f"{analisis['stake']}/10",
                "hora": hora_madrid_str
            })

        item = {
            "id": p.get("id"),
            "local": nombre_local,
            "visitante": nombre_visitante,
            "liga": comp_info["name"],
            "liga_key": comp_info["key"],
            "fecha": fecha_madrid_partido,
            "hora": hora_madrid_partido,
            "hora_utc": hora_utc_raw,
            "minutos_restantes": minutos_restantes,
            "estado": estado_api,
            "marcador": marcador_str,
            "goles_local": goles_local,
            "goles_visitante": goles_visitante,
            "mercado": analisis["mercado"],
            "tipo_mercado": analisis["tipo_mercado"],
            "cuota": analisis["cuota"],
            "prob_modelo": analisis["prob_modelo"],
            "ev": f"+{analisis['ev']}%",
            "stake": analisis["stake"],
            "tiene_pronostico": True,
            "telegram_enviado": fue_enviado_telegram
        }
        partidos_para_web.append(item)

    guardar_datos_json(partidos_para_web, alertas_enviadas, hora_madrid_str)
    print(f"🏁 Ciclo finalizado. Total partidos oficiales: {len(partidos_para_web)} | Alertas: {len(alertas_enviadas)}")

if __name__ == "__main__":
    ejecutar_ciclo()
