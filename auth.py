"""
Flujo OAuth de TikTok Marketing API
Genera el access_token y lo guarda automáticamente en el .env

Uso:
    python auth.py
"""

import os
import re
import json
import webbrowser
import requests
from dotenv import load_dotenv, set_key

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_FILE)

APP_ID = os.environ.get("TIKTOK_APP_ID", "").strip()
APP_SECRET = os.environ.get("TIKTOK_APP_SECRET", "").strip()

TOKEN_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"


def build_auth_url() -> str:
    redirect = "https://tepuycenter.com/"
    return (
        f"https://business-api.tiktok.com/portal/auth"
        f"?app_id={APP_ID}"
        f"&state=mcp_local"
        f"&redirect_uri={requests.utils.quote(redirect, safe='')}"
    )


def extract_auth_code(raw: str) -> str:
    """Extrae el auth_code de una URL completa o lo devuelve si ya es el código."""
    raw = raw.strip()
    match = re.search(r"auth_code=([^&\s]+)", raw)
    if match:
        return match.group(1)
    # Si el usuario pegó solo el código directamente
    if raw and " " not in raw and "http" not in raw:
        return raw
    raise ValueError("No se encontró auth_code en el texto pegado.")


def exchange_code_for_token(auth_code: str) -> dict:
    payload = {
        "app_id": APP_ID,
        "secret": APP_SECRET,
        "auth_code": auth_code,
    }
    resp = requests.post(TOKEN_URL, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Error de TikTok: {data.get('message')} (code {data.get('code')})")
    return data["data"]


def save_to_env(key: str, value: str):
    set_key(ENV_FILE, key, value)
    print(f"  ✅ {key} guardado en .env")


def main():
    print("=" * 55)
    print("  TikTok Ads — Obtener Access Token")
    print("=" * 55)

    # Validar que el .env tiene App ID y Secret
    if not APP_ID or not APP_SECRET:
        print("\n❌ Faltan TIKTOK_APP_ID o TIKTOK_APP_SECRET en el .env")
        print("   Completa esos dos valores primero y vuelve a correr este script.")
        return

    print(f"\n✔ App ID: {APP_ID}")
    print(f"✔ Secret: {APP_SECRET[:6]}{'*' * (len(APP_SECRET) - 6)}")

    auth_url = build_auth_url()

    print("\n📋 PASO 1: Autoriza la app en el navegador")
    print("-" * 55)
    print("Se va a abrir esta URL:")
    print(f"\n  {auth_url}\n")
    input("Presiona ENTER para abrir el navegador...")
    webbrowser.open(auth_url)

    print("\n📋 PASO 2: Copia la URL a la que fuiste redirigido")
    print("-" * 55)
    print("Después de autorizar, TikTok te redirige a tepuycenter.com")
    print("La URL tendrá algo así:")
    print("  https://tepuycenter.com/?auth_code=XXXX&state=mcp_local")
    print("\nCopia ESA URL completa (o solo el valor del auth_code) y pégala aquí:")
    raw_input = input("\n> ").strip()

    try:
        auth_code = extract_auth_code(raw_input)
        print(f"\n✔ auth_code detectado: {auth_code[:8]}...")
    except ValueError as e:
        print(f"\n❌ {e}")
        return

    print("\n📋 PASO 3: Intercambiando código por access_token...")
    print("-" * 55)
    try:
        token_data = exchange_code_for_token(auth_code)
    except Exception as e:
        print(f"\n❌ Error al obtener el token: {e}")
        return

    access_token = token_data.get("access_token", "")
    advertiser_ids = token_data.get("advertiser_ids", [])

    print(f"\n✅ access_token obtenido: {access_token[:12]}...")
    if advertiser_ids:
        print(f"✅ Advertiser IDs encontrados: {advertiser_ids}")

    # Guardar en .env
    print("\n💾 Guardando en .env...")
    save_to_env("TIKTOK_ACCESS_TOKEN", access_token)

    if advertiser_ids and not os.environ.get("TIKTOK_ADVERTISER_ID"):
        if len(advertiser_ids) == 1:
            save_to_env("TIKTOK_ADVERTISER_ID", str(advertiser_ids[0]))
        else:
            print(f"\n⚠️  Hay varios Advertiser IDs: {advertiser_ids}")
            chosen = input("¿Cuál quieres usar? Pega el ID: ").strip()
            save_to_env("TIKTOK_ADVERTISER_ID", chosen)

    print("\n" + "=" * 55)
    print("  ¡Listo! Ya puedes arrancar el servidor MCP:")
    print("  python server.py")
    print("=" * 55)


if __name__ == "__main__":
    main()
