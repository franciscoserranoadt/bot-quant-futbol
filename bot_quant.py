import os
import requests
from datetime import datetime, timezone

# Credenciales de GitHub Secrets
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def enviar_telegram(mensaje):
    print(f"Intentando enviar a Telegram con Chat ID: {TELEGRAM_CHAT_ID}...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID están vacíos en Secrets.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"Respuesta Telegram: Status {res.status_code} - {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Excepción conectando con Telegram: {e}")
        return False

def ejecutar():
    hora_actual = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
    print(f"--- Ejecutando prueba forzada a las {hora_actual} ---")
    
    mensaje = (
        f"🤖 <b>APEX QUANT BOT — PRUEBA DE CONEXIÓN INMEDIATA</b>\n\n"
        f"✅ <b>Estado:</b> ¡Conexión con Telegram 100% confirmada!\n"
        f"🕒 <b>Hora Servidor:</b> {hora_actual}\n"
        f"📱 <b>Dispositivo:</b> Tu móvil recibe alertas correctamente.\n\n"
        f"⚡ <i>GitHub Actions y Telegram están vinculados con éxito.</i>"
    )
    enviar_telegram(mensaje)

if __name__ == "__main__":
    ejecutar()
