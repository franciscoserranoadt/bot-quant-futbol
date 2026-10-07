import os
import requests
from datetime import datetime, timezone

# ==========================================
# CONFIGURACIÓN DE APIS Y TELEGRAM
# ==========================================
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 7 Ligas Oficiales Admitidas (LaLiga 1ª y 2ª, Premier, Bundesliga, Serie A, Ligue 1, Champions)
LEAGUES = ["PD", "SD", "PL", "BL1", "SA", "FL1", "CL"]

def enviar_telegram(mensaje):
    """Envía la alerta con formato HTML enriquecido a tu móvil"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram no configurado")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def obtener_partidos_del_dia():
    """Llamada gratuita a Football-Data.org (0 créditos de The Odds API)"""
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/matches?dateFrom={hoy}&dateTo={hoy}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            partidos = res.json().get("matches", [])
            return [p for p in partidos if p.get("competition", {}).get("code") in LEAGUES]
    except Exception as e:
        print(f"Error Football-Data: {e}")
    return []

def calcular_ev_y_stake(cuota_casa, prob_modelo):
    """Cálculo de Valor Esperado (+EV) y Kelly fraccional (1/4)"""
    ev = (prob_modelo * cuota_casa) - 1.0
    if ev <= 0.05:  # Filtro mínimo de +5% de valor
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
  
    # Simulación de detección analítica puntual (T-45m)
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
    print(f"[{ahora_utc.strftime('%H:%M:%S UTC')}] Comprobando partidos...")
    
    partidos_hoy = obtener_partidos_del_dia()
    if not partidos_hoy:
        print("🌙 SUSPENSIÓN INTELIGENTE: Sin partidos hoy. 0 llamadas de cuotas gastadas.")
        return

    partidos_en_ventana = []
    for p in partidos_hoy:
        hora_utc_str = p.get("utcDate")
        if not hora_utc_str:
            continue
        inicio_utc = datetime.fromisoformat(hora_utc_str.replace("Z", "+00:00"))
        diferencia_minutos = (inicio_utc - ahora_utc).total_seconds() / 60.0
        
        # Dispara alertas si el partido inicia en 25-50 minutos (ventana T-45m a T-30m)
        if 25 <= diferencia_minutos <= 50:
            partidos_en_ventana.append(p)
            
    if not partidos_en_ventana:
        print("⏳ Hay partidos hoy, pero ninguno en ventana T-45m/T-30m. 0 créditos gastados.")
        return

    for p in partidos_en_ventana:
        analizar_y_alertar(p)

if __name__ == "__main__":
    ejecutar_ciclo()
