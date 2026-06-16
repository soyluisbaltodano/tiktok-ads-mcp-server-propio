"""
Cliente para la TikTok Marketing API v1.3
Documentación: https://business-api.tiktok.com/portal/docs
"""

import os
import time
import requests

BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"

# Cuántas veces reintentar si TikTok devuelve rate limit (429) antes de rendirse
_MAX_RETRIES = 3
# Segundos de espera base; se duplica en cada intento (1s → 2s → 4s)
_RETRY_BASE_DELAY = 1.0


def _headers() -> dict:
    """Construye los headers de autenticación requeridos por TikTok."""
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("TIKTOK_ACCESS_TOKEN no está configurado en el .env")
    return {
        "Access-Token": token,
        "Content-Type": "application/json",
    }


def _advertiser_id() -> str:
    """Devuelve el Advertiser ID desde las variables de entorno."""
    adv_id = os.environ.get("TIKTOK_ADVERTISER_ID", "")
    if not adv_id:
        raise ValueError("TIKTOK_ADVERTISER_ID no está configurado en el .env")
    return adv_id


def _post(endpoint: str, body: dict) -> dict:
    """Realiza una petición POST a la API con reintentos automáticos."""
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(_MAX_RETRIES):
        response = requests.post(url, headers=_headers(), json=body, timeout=15)

        if response.status_code == 429:
            wait = _RETRY_BASE_DELAY * (2 ** attempt)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
                continue
            raise RuntimeError("TikTok API rate limit: demasiadas peticiones.")

        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            msg = data.get("message", "Error desconocido de la API")
            raise RuntimeError(f"TikTok API error {data.get('code')}: {msg}")

        return data.get("data", {})

    raise RuntimeError("No se pudo completar la petición después de varios intentos.")


def _get(endpoint: str, params: dict) -> dict:
    """Realiza una petición GET a la API con reintentos automáticos ante rate limit."""
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(_MAX_RETRIES):
        response = requests.get(url, headers=_headers(), params=params, timeout=15)

        # 429 = rate limit alcanzado → esperar y reintentar
        if response.status_code == 429:
            wait = _RETRY_BASE_DELAY * (2 ** attempt)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
                continue
            raise RuntimeError(f"TikTok API rate limit: demasiadas peticiones. Espera unos segundos y vuelve a intentar.")

        response.raise_for_status()
        data = response.json()

        # La API de TikTok devuelve code=0 cuando todo está bien
        if data.get("code") != 0:
            msg = data.get("message", "Error desconocido de la API")
            raise RuntimeError(f"TikTok API error {data.get('code')}: {msg}")

        return data.get("data", {})

    # Este punto no debería alcanzarse, pero por seguridad:
    raise RuntimeError("No se pudo completar la petición después de varios intentos.")


# ── Funciones públicas (una por herramienta MCP) ──────────────────────────────

def get_advertiser_info() -> dict:
    """Información básica de la cuenta anunciante."""
    adv_id = _advertiser_id()
    return _get("/advertiser/info/", {
        "advertiser_ids": f'["{adv_id}"]',
    })


def get_campaigns(status_filter: str = "ALL") -> dict:
    """
    Lista las campañas del anunciante.
    status_filter: ALL | ENABLE | DISABLE | DELETE
    """
    return _get("/campaign/get/", {
        "advertiser_id": _advertiser_id(),
        "primary_status": status_filter,
        "page_size": 100,
    })


def get_adgroups(campaign_id: str | None = None) -> dict:
    """
    Lista los ad groups. Si se pasa campaign_id, filtra por campaña.
    """
    params: dict = {
        "advertiser_id": _advertiser_id(),
        "page_size": 100,
    }
    if campaign_id:
        params["campaign_ids"] = f'["{campaign_id}"]'
    return _get("/adgroup/get/", params)


def get_ads(adgroup_id: str | None = None) -> dict:
    """
    Lista los anuncios. Si se pasa adgroup_id, filtra por ad group.
    """
    params: dict = {
        "advertiser_id": _advertiser_id(),
        "page_size": 100,
    }
    if adgroup_id:
        params["adgroup_ids"] = f'["{adgroup_id}"]'
    return _get("/ad/get/", params)


def get_report(
    start_date: str,
    end_date: str,
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
) -> dict:
    """
    Reporte de rendimiento integrado.
    start_date / end_date: formato 'YYYY-MM-DD'
    metrics por defecto: spend, impressions, clicks, ctr, cpc
    dimensions por defecto: campaign_id, stat_time_day
    """
    if metrics is None:
        metrics = ["spend", "impressions", "clicks", "ctr", "cpc", "reach"]
    if dimensions is None:
        dimensions = ["campaign_id", "stat_time_day"]

    import json
    return _get("/report/integrated/get/", {
        "advertiser_id": _advertiser_id(),
        "report_type": "BASIC",
        "dimensions": json.dumps(dimensions),
        "metrics": json.dumps(metrics),
        "start_date": start_date,
        "end_date": end_date,
        "page_size": 100,
    })


def update_campaign_status(campaign_id: str, status: str) -> dict:
    """
    Activa o pausa una campaña.
    status: ENABLE (activar) | DISABLE (pausar) | DELETE (eliminar)
    """
    return _post("/campaign/status/update/", {
        "advertiser_id": _advertiser_id(),
        "campaign_ids": [campaign_id],
        "opt_status": status,
    })


def update_campaign_budget(campaign_id: str, budget: float) -> dict:
    """
    Cambia el presupuesto de una campaña.
    budget: monto en la moneda de la cuenta (ej: 50.0 = $50)
    """
    return _post("/campaign/update/budget/", {
        "advertiser_id": _advertiser_id(),
        "budget_list": [{"campaign_id": campaign_id, "budget": budget}],
    })


def update_adgroup_status(adgroup_id: str, status: str) -> dict:
    """
    Activa o pausa un ad group.
    status: ENABLE (activar) | DISABLE (pausar) | DELETE (eliminar)
    """
    return _post("/adgroup/status/update/", {
        "advertiser_id": _advertiser_id(),
        "adgroup_ids": [adgroup_id],
        "opt_status": status,
    })


def update_ad_status(ad_id: str, status: str) -> dict:
    """
    Activa o pausa un anuncio individual.
    status: ENABLE (activar) | DISABLE (pausar) | DELETE (eliminar)
    """
    return _post("/ad/status/update/", {
        "advertiser_id": _advertiser_id(),
        "ad_ids": [ad_id],
        "opt_status": status,
    })
