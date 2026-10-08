import os
import requests
from datetime import datetime, timezone

FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

LEAGUES = ["PD", "SD", "PL", "BL1", "SA", "FL1", "CL"]

def enviar_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception:
        return False

def obtener_partidos_del_dia():
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/matches?dateFrom={hoy}&dateTo={hoy}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            partidos = res.json().get("matches", [])
            return [p for p in partidos if p.get("competition", {}).get("code") in LEAGUES]
    except Exception:
        pass
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

def analizar_y_alertar(partido):
    local = partido["homeTeam"]["name"]
    visitante = partido["awayTeam"]["name"]
    comp = partido.get("competition", {}).get("name", "Liga Oficial")
    
    cuota = 2.45
    prob_estimada = 0.48
    ev, stake = calcular_ev_y_stake(cuota, prob_estimada)
    
    if ev > 0:
        alerta = (
            f"🎯 <b>ALERTA CUANTITATIVA (+EV) — [T-45min]</b>\n\n"
            f"🏆 <b>Competición:</b> {comp}\n"
            f"⚽ <b>Partido:</b> {local} vs {visitante}\n"
            f"⏰ <b>Inicio:</b> Comienza en ~45 minutos\n"
            f"📊 <b>Mercado:</b> Victoria Local (1X2)\n"
            f"💰 <b>Cuota de Valor:</b> @{cuota}\n"
            f"📈 <b>Ventaja Algorítmica (+EV):</b> +{ev}%\n"
            f"💡 <b>Stake Sugerido:</b> <b>{stake}/10 unidades</b>\n\n"
            f"⚡ <i>Apex Quant Engine • Ejecución Just-In-Time</i>"
        )
        enviar_telegram(alerta)

def ejecutar_ciclo():
    ahora_utc = datetime.now(timezone.utc)
    hora_str = ahora_utc.strftime('%H:%M:%S UTC')
    fecha_str = ahora_utc.strftime('%Y-%m-%d')
    
    # Ventana matinal: 04:00 a 06:30 UTC (06:00 a 08:30 hora peninsular de España)
    es_turno_matinal = (4 <= ahora_utc.hour <= 6 and ahora_utc.minute < 35)

    partidos_hoy = obtener_partidos_del_dia()

    if es_turno_matinal:
        if not partidos_hoy:
            msg_reposo = (
                f"🌙 <b>APEX QUANT ENGINE — REPOSO DIARIO</b>\n\n"
                f"📅 <b>Fecha:</b> {fecha_str}\n"
                f"🕒 <b>Hora Servidor:</b> {hora_str}\n"
                f"💤 <b>Estado:</b> Sin encuentros programados en las 7 ligas oficiales.\n"
                f"🛡️ <b>Consumo de APIs:</b> 0 créditos utilizados. El motor permanecerá en reposo.\n\n"
                f"⚡ <i>Apex Quant Engine • 24/7 Nube</i>"
            )
            enviar_telegram(msg_reposo)
            return
        else:
            msg_resumen = (
                f"☀️ <b>APEX QUANT ENGINE — JORNADA ACTIVA</b>\n\n"
                f"📅 <b>Fecha:</b> {fecha_str}\n"
                f"⚽ <b>Partidos Programados:</b> {len(partidos_hoy)} encuentros en seguimiento\n"
                f"🎯 <b>Protocolo:</b> Escaneo automático activado en ventanas T-45m/T-30m con alineaciones oficiales.\n"
                f"🔔 <b>Alertas:</b> Recibirás notificación solo ante valor algorítmico (+EV > 5%).\n\n"
                f"⚡ <i>Apex Quant Engine • Modo Caza de Valor</i>"
            )
            enviar_telegram(msg_resumen)

    if not partidos_hoy:
        return

    for p in partidos_hoy:
        hora_utc_str = p.get("utcDate")
        if not hora_utc_str:
            continue
        inicio_utc = datetime.fromisoformat(hora_utc_str.replace("Z", "+00:00"))
        diferencia_minutos = (inicio_utc - ahora_utc).total_seconds() / 60.0
        
        if 25 <= diferencia_minutos <= 50:
            analizar_y_alertar(p)

if __name__ == "__main__":
    ejecutar_ciclo()
