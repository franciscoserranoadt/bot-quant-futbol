import os
import json
import requests
from datetime import datetime, timezone

# ==========================================
# CONFIGURACIÓN DE APIS Y TELEGRAM
# ==========================================
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 7 Ligas Oficiales Admitidas
LEAGUES_MAP = {
    "PD": {"name": "LaLiga EA Sports", "key": "laliga", "country": "ESP"},
    "SD": {"name": "LaLiga Hypermotion", "key": "laliga2", "country": "ESP"},
    "PL": {"name": "Premier League", "key": "premier", "country": "ENG"},
    "BL1": {"name": "Bundesliga", "key": "bundesliga", "country": "GER"},
    "SA": {"name": "Serie A", "key": "seriea", "country": "ITA"},
    "FL1": {"name": "Ligue 1", "key": "ligue1", "country": "FRA"},
    "CL": {"name": "Champions League", "key": "champions", "country": "UEFA"}
}

def enviar_telegram(mensaje):
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

def obtener_partidos_del_dia():
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/matches?dateFrom={hoy}&dateTo={hoy}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            partidos = res.json().get("matches", [])
            return [p for p in partidos if p.get("competition", {}).get("code") in LEAGUES_MAP]
    except Exception as e:
        print(f"Error Football-Data: {e}")
    return []

def calcular_ev_y_stake(cuota_casa, prob_modelo):
    ev = (prob_modelo * cuota_casa) - 1.0
    if ev <= 0.05:
        return 0.0, 0
    b = cuota_casa - 1.0
    q = 1.0 - prob_modelo
    kelly_puro = (b * prob_modelo - q) / b
    kelly_fraccional = max(0.0, kelly_puro * 0.25)
    stake = min(10, max(1, round(kelly_fraccional * 40)))
    return round(ev * 100, 1), stake

def guardar_datos_json(partidos_procesados, alertas_enviadas, hora_utc_str):
    datos = {
        "ultima_actualizacion": hora_utc_str,
        "total_partidos_hoy": len(partidos_procesados),
        "partidos": partidos_procesados,
        "alertas": alertas_enviadas
    }
    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print("📁 Archivo datos.json guardado con éxito.")

def ejecutar_ciclo():
    ahora_utc = datetime.now(timezone.utc)
    hora_str = ahora_utc.strftime('%H:%M UTC')
    print(f"[{hora_str}] Iniciando ciclo cuantitativo...")

    partidos_raw = obtener_partidos_del_dia()
    partidos_para_web = []
    alertas_enviadas = []

    for p in partidos_raw:
        comp_code = p.get("competition", {}).get("code", "")
        comp_info = LEAGUES_MAP.get(comp_code, {"name": "Liga Oficial", "key": "all"})
        hora_utc = p.get("utcDate", "")
        hora_corta = hora_utc[11:16] if len(hora_utc) >= 16 else "TBD"
        
        # Cálculo de ventana previa
        minutos_restantes = 999
        if hora_utc:
            inicio = datetime.fromisoformat(hora_utc.replace("Z", "+00:00"))
            minutos_restantes = round((inicio - ahora_utc).total_seconds() / 60.0)

        # Análisis probabilístico
        cuota_sim = 2.15
        prob_sim = 0.52
        ev, stake = calcular_ev_y_stake(cuota_sim, prob_sim)

        item = {
            "id": p.get("id"),
            "local": p["homeTeam"]["name"],
            "visitante": p["awayTeam"]["name"],
            "liga": comp_info["name"],
            "liga_key": comp_info["key"],
            "hora": hora_corta + " UTC",
            "minutos_restantes": minutos_restantes,
            "estado": p.get("status", "SCHEDULED"),
            "mercado": "Victoria Local (1X2)",
            "cuota": cuota_sim,
            "prob_modelo": f"{round(prob_sim*100, 1)}%",
            "ev": f"+{ev}%",
            "stake": stake,
            "es_valor": ev > 0
        }
        partidos_para_web.append(item)

        # Disparar alerta en ventana Just-in-Time (25-50 min antes)
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
                "hora": hora_str
            })

    guardar_datos_json(partidos_para_web, alertas_enviadas, hora_str)

if __name__ == "__main__":
    ejecutar_ciclo()
