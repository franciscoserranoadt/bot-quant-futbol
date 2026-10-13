import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# Credenciales automáticas desde los Secrets del repositorio
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
APP_URL = "https://franciscoserranoadt.github.io/bot-quant-futbol/"
TZ_MADRID = ZoneInfo("Europe/Madrid")

def probar_alerta():
    hora_str = datetime.now(TZ_MADRID).strftime("%H:%M Madrid")
    print(f"[{hora_str}] Iniciando prueba directa de alerta a Telegram...")
    print(f"Destino TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Error: Faltan credenciales de Telegram en las variables de entorno.")
        return

    # Mensaje idéntico al formato oficial enriquecido de Apex Quant Pro
    msg = (
        "╔═══════════════════════════════════════╗\n"
        "║ 🎯 <b>ALERTA CUANTITATIVA (+EV) — TEST</b>\n"
        "║ 🇪🇸 <b>LALIGA EA SPORTS</b>\n"
        "╚═══════════════════════════════════════╝\n\n"
        "⚽ <b>PARTIDO:</b>\n"
        "🛡️ <b>Real Madrid CF</b> vs 🛡️ <b>FC Barcelona</b>\n"
        f"⏰ <b>Hora Escaneo:</b> <b>{hora_str}</b>\n\n"
        "🥅 <b>MERCADO SELECCIONADO:</b>\n"
        "👉 <b>Más de 2.5 Goles (Over 2.5)</b>\n\n"
        "💰 <b>Cuota de Valor:</b> <b>@2.15</b>\n"
        "📈 <b>Ventaja Algorítmica:</b> <b>+38.5%</b> 💎 <b>[VALOR ÉLITE +EV]</b>\n"
        "📊 <b>Intensidad Modelo:</b> 🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜ (<b>68.5%</b>)\n"
        "💎 <b>Ventaja CLV:</b> +6.2%\n\n"
        "⚡ <b>GESTIÓN DE BANCA (KELLY FRACCIONAL):</b>\n"
        "💡 <b>Stake Sugerido:</b> <b>4/10 U</b>\n"
        "📊 <b>Asignación:</b> ▰▰▰▰▱▱▱▱▱▱\n"
        "📈 <b>Dinámica:</b> 🔥 Racha Favorable Local (+Dinámica)\n\n"
        "───────────────────────────────────────\n"
        "⚡ <i>Apex Quant Engine • Prueba de Conexión Verificada</i>"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "📱 Ver en Vivo en la Web App", "url": APP_URL}]
            ]
        }
    }

    try:
        r = requests.post(url, json=payload, timeout=12)
        print(f"Código HTTP de respuesta: {r.status_code}")
        print(f"Respuesta de Telegram: {r.text}")
        if r.status_code == 200:
            print("🎉 ¡Éxito! Alerta de prueba enviada y recibida en Telegram.")
        else:
            print("⚠️ Revisa que el bot tenga permisos de administrador en el canal.")
    except Exception as e:
        print(f"❌ Error al conectar con Telegram: {e}")

if __name__ == "__main__":
    probar_alerta()
