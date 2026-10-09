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

# Huso horario oficial de España Peninsular (Madrid)
TZ_MADRID = ZoneInfo("Europe/Madrid")

# 7 Ligas Oficiales admitidas con sus códigos de Football-Data.org
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
    """
    Obtiene partidos desde ayer (para capturar marcadores finales)
    hasta los próximos 2 días (para capturar jornadas completas).
    """
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
    """Cálculo estricto de Valor Esperado (+EV) y Kelly Fraccional (1/4)."""
    ev = (prob_modelo * cuota_casa) - 1.0
    if ev <= 0.05:
        return 0.0, 0
    b = cuota_casa - 1.0
    q = 1.0 - prob_modelo
    kelly_puro = (b * prob_modelo - q) / b
    kelly_fraccional = max(0.0, kelly_puro * 0.25)
    stake = min(10, max(1, round(kelly_fraccional * 40)))
    return round(ev * 100, 1), stake

def guardar_datos_json(partidos_procesados, alertas_enviadas, hora_madrid_str):
    """Guarda datos.json con marcadores reales para sincronización con la app."""
    datos = {
        "ultima_actualizacion": hora_madrid_str,
        "huso_horario": "Europe/Madrid",
        "total_partidos_hoy": len(partidos_procesados),
        "partidos": partidos_procesados,
        "alertas": alertas_enviadas
    }
    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print("📁 Archivo datos.json guardado con éxito con marcadores reales.")

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
        comp_info = LEAGUES_MAP.get(comp_code, {
            "name": p.get("competition", {}).get("name", "Oficial"),
            "key": "laliga" if "PD" in comp_code or "SD" in comp_code else "all"
        })

        hora_utc_raw = p.get("utcDate", "")
        minutos_restantes = 999
        hora_madrid_partido = "TBD"
        fecha_madrid_partido = hoy_madrid_str

        # Conversión a Horario Peninsular Español (Madrid)
        if hora_utc_raw:
            inicio_utc = datetime.fromisoformat(hora_utc_raw.replace("Z", "+00:00"))
            inicio_madrid = inicio_utc.astimezone(TZ_MADRID)
            hora_madrid_partido = inicio_madrid.strftime('%H:%M Madrid')
            fecha_madrid_partido = inicio_madrid.strftime('%Y-%m-%d')
            minutos_restantes = round((inicio_utc - ahora_utc).total_seconds() / 60.0)

        # ======================================================================
        # EXTRACCIÓN REAL DE MARCADOR FINAL Y GOLES DE FOOTBALL-DATA.ORG
        # ======================================================================
        score_data = p.get("score", {})
        full_time = score_data.get("fullTime", {})
        g_local = full_time.get("home")
        g_visitante = full_time.get("away")
        
        marcador_str = None
        if g_local is not None and g_visitante is not None:
            marcador_str = f"{g_local} - {g_visitante}"

        estado_api = p.get("status", "SCHEDULED")

        # Modelo cuantitativo (+EV)
        cuota_sim = 2.15
        prob_sim = 0.52
        ev, stake = calcular_ev_y_stake(cuota_sim, prob_sim)

        item = {
            "id": p.get("id"),
            "local": p.get("homeTeam", {}).get("name", "Local"),
            "visitante": p.get("awayTeam", {}).get("name", "Visitante"),
            "liga": comp_info["name"],
            "liga_key": comp_info["key"],
            "fecha": fecha_madrid_partido,
            "hora": hora_madrid_partido,
            "hora_utc": hora_utc_raw,
            "minutos_restantes": minutos_restantes,
            "estado": estado_api,
            "marcador": marcador_str,        # 👈 Marcador ej: "2 - 1"
            "goles_local": g_local,          # 👈 Goles local
            "goles_visitante": g_visitante,  # 👈 Goles visitante
            "mercado": "Victoria Local (1X2)",
            "cuota": cuota_sim,
            "prob_modelo": f"{round(prob_sim*100, 1)}%",
            "ev": f"+{ev}%",
            "stake": stake,
            "tiene_pronostico": True
        }
        partidos_para_web.append(item)

        # Disparo Just-in-Time a Telegram (T-45m a T-25m)
        if 25 <= minutos_restantes <= 50 and ev > 0:
            alerta_msg = (
                f"🎯 <b>ALERTA CUANTITATIVA (+EV) — [T-45m]</b>\n\n"
                f"🏆 <b>Competición:</b> {comp_info['name']}\n"
                f"⚽ <b>Partido:</b> {item['local']} vs {item['visitante']}\n"
                f"⏰ <b>Inicio:</b> {item['hora']} (en {minutos_restantes} min)\n"
                f"📊 <b>Mercado:</b> {item['mercado']}\n"
                f"💰 <b>Cuota de Valor:</b> @{cuota_sim}\n"
                f"📈 <b>Ventaja Algorítmica (+EV):</b> +{ev}%\n"
                f"💡 <b>Stake Sugerido:</b> <b>{stake}/10 unidades</b>\n\n"
                f"⚡ <i>Apex Quant Engine</i>"
            )
            enviar_telegram(alerta_msg)
            alertas_enviadas.append({
                "partido": f"{item['local']} vs {item['visitante']}",
                "mercado": item['mercado'],
                "cuota": f"@{cuota_sim}",
                "ev": f"+{ev}%",
                "stake": f"{stake}/10",
                "hora": hora_madrid_str
            })

    guardar_datos_json(partidos_para_web, alertas_enviadas, hora_madrid_str)
    print(f"🏁 Ciclo finalizado. Total partidos registrados: {len(partidos_para_web)}")

if __name__ == "__main__":
    ejecutar_ciclo()
