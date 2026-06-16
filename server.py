import os
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

load_dotenv(Path(__file__).parent / ".env")

import tiktok.client as tiktok

mcp = FastMCP(
    "tiktok-ads",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


# ── Herramientas ──────────────────────────────────────────────────────────────

@mcp.tool()
def get_advertiser_info() -> dict:
    """
    Devuelve la información básica de la cuenta anunciante de TikTok:
    nombre, zona horaria, moneda, balance, estado.
    """
    return tiktok.get_advertiser_info()


@mcp.tool()
def get_campaigns(status_filter: str = "ALL") -> dict:
    """
    Lista las campañas de TikTok Ads.

    Args:
        status_filter: Estado de las campañas a consultar.
                       Valores válidos: ALL, ENABLE, DISABLE, DELETE.
                       Por defecto devuelve todas (ALL).
    """
    return tiktok.get_campaigns(status_filter=status_filter)


@mcp.tool()
def get_adgroups(campaign_id: str = "") -> dict:
    """
    Lista los ad groups (conjuntos de anuncios).

    Args:
        campaign_id: ID de campaña para filtrar. Deja vacío para ver todos.
    """
    return tiktok.get_adgroups(campaign_id=campaign_id or None)


@mcp.tool()
def get_ads(adgroup_id: str = "") -> dict:
    """
    Lista los anuncios individuales.

    Args:
        adgroup_id: ID de ad group para filtrar. Deja vacío para ver todos.
    """
    return tiktok.get_ads(adgroup_id=adgroup_id or None)


@mcp.tool()
def get_report(
    start_date: str,
    end_date: str,
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
) -> dict:
    """
    Obtiene el reporte de rendimiento de las campañas.

    Args:
        start_date: Fecha de inicio en formato YYYY-MM-DD (ej: '2026-05-01').
        end_date:   Fecha de fin   en formato YYYY-MM-DD (ej: '2026-05-23').
        metrics:    Lista de métricas. Por defecto: spend, impressions, clicks,
                    ctr, cpc, reach. Otras: conversions, cost_per_conversion, etc.
        dimensions: Lista de dimensiones. Por defecto: campaign_id, stat_time_day.
    """
    return tiktok.get_report(
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
        dimensions=dimensions,
    )


def build_http_app():
    """
    App ASGI para Render.com con OAuth simulado.
    NO modificar — ya está probada y funcionando.
    """
    import uuid
    from starlette.requests import Request
    from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.middleware.cors import CORSMiddleware

    mcp_asgi = mcp.streamable_http_app()

    class OAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path

            if path == "/.well-known/oauth-authorization-server":
                base = str(request.base_url).rstrip("/")
                return JSONResponse({
                    "issuer": base,
                    "authorization_endpoint": f"{base}/oauth/authorize",
                    "token_endpoint": f"{base}/oauth/token",
                    "registration_endpoint": f"{base}/oauth/register",
                    "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code"],
                    "code_challenge_methods_supported": ["S256"],
                })

            if path == "/oauth/register":
                body = await request.json()
                return JSONResponse({
                    "client_id": str(uuid.uuid4()),
                    "client_secret": str(uuid.uuid4()),
                    "redirect_uris": body.get("redirect_uris", []),
                    "grant_types": ["authorization_code"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_post",
                }, status_code=201)

            if path == "/oauth/authorize":
                if request.method == "GET":
                    p = request.query_params
                    redirect_uri = p.get("redirect_uri", "")
                    state = p.get("state", "")
                    code = str(uuid.uuid4())
                    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Autorizar MCP</title>
<style>
  body{{font-family:-apple-system,Arial,sans-serif;max-width:420px;margin:80px auto;padding:20px;background:#f8fafc;text-align:center}}
  .card{{background:white;padding:40px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
  h2{{color:#1e293b}} p{{color:#64748b;margin-bottom:28px}}
  button{{background:#2563eb;color:white;padding:12px 32px;border:none;border-radius:8px;font-size:16px;cursor:pointer;width:100%}}
  button:hover{{background:#1d4ed8}}
</style></head>
<body><div class="card">
  <div style="font-size:48px;margin-bottom:16px">🔌</div>
  <h2>Autorizar TikTok Ads MCP</h2>
  <p>Claude Desktop quiere conectarse a este servidor MCP.</p>
  <form method="post">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="state" value="{state}">
    <input type="hidden" name="code" value="{code}">
    <button type="submit">Autorizar acceso</button>
  </form>
</div></body></html>"""
                    return HTMLResponse(html)
                form = await request.form()
                redirect_uri = form.get("redirect_uri", "")
                state = form.get("state", "")
                code = form.get("code", str(uuid.uuid4()))
                sep = "&" if "?" in redirect_uri else "?"
                return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}", status_code=302)

            if path == "/oauth/token":
                return JSONResponse({
                    "access_token": str(uuid.uuid4()),
                    "token_type": "bearer",
                    "expires_in": 31536000,
                })

            return await call_next(request)

    app = OAuthMiddleware(mcp_asgi)
    app = CORSMiddleware(app, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    return app


if __name__ == "__main__":
    import sys
    sys.stderr.reconfigure(encoding="utf-8")

    port = int(os.getenv("PORT", 8000))

    if "PORT" in os.environ:
        import uvicorn
        uvicorn.run(build_http_app(), host="0.0.0.0", port=port)
    else:
        missing = [
            var for var in ["TIKTOK_ACCESS_TOKEN", "TIKTOK_ADVERTISER_ID"]
            if not os.environ.get(var)
        ]
        if missing:
            print(f"[!] Faltan variables en .env: {', '.join(missing)}", file=sys.stderr)
        else:
            print("[OK] Credenciales cargadas -- arrancando MCP...", file=sys.stderr)
        mcp.run()
