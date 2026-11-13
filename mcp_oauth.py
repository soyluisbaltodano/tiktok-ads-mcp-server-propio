import base64
import hashlib
import hmac
import html
import json
import os
import time
import uuid
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign_token(secret: str, payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64 = _b64url_encode(raw)
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).digest()
    return f"{b64}.{_b64url_encode(sig)}"


def _verify_token(secret: str, token: str) -> dict | None:
    if not token or "." not in token:
        return None
    try:
        b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(b64).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _base_url(request: Request) -> str:
    proto = (
        request.headers.get("x-forwarded-proto", request.url.scheme)
        .split(",")[0]
        .strip()
    )
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    ).split(",")[0].strip()
    return f"{proto}://{host}".rstrip("/")


def _valid_redirect_uri(uri: str) -> bool:
    return (
        uri.startswith("https://")
        or uri.startswith("http://localhost")
        or uri.startswith("http://127.0.0.1")
    )


def _render_authorize_html(
    title: str,
    subtitle: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    code_challenge_method: str,
    error: str = "",
) -> str:
    err_html = (
        f'<div class="err">{html.escape(error)}</div>' if error else ""
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body{{font-family:-apple-system,Arial,sans-serif;max-width:420px;margin:60px auto;padding:20px;background:#f8fafc;text-align:center}}
  .card{{background:white;padding:36px 32px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
  h2{{color:#1e293b;margin:0 0 8px}} p{{color:#64748b;margin:0 0 24px;font-size:15px}}
  input[type=password]{{width:100%;box-sizing:border-box;padding:12px 14px;border:1px solid #cbd5e1;border-radius:8px;font-size:15px;margin-bottom:14px}}
  button{{background:#2563eb;color:white;padding:12px 24px;border:none;border-radius:8px;font-size:16px;cursor:pointer;width:100%;font-weight:600}}
  button:hover{{background:#1d4ed8}}
  .err{{background:#fee2e2;color:#b91c1c;padding:10px 12px;border-radius:8px;font-size:14px;margin-bottom:14px}}
</style></head>
<body><div class="card">
  <h2>{html.escape(title)}</h2>
  <p>{html.escape(subtitle)}</p>
  {err_html}
  <form method="post">
    <input type="hidden" name="redirect_uri" value="{html.escape(redirect_uri, quote=True)}">
    <input type="hidden" name="state" value="{html.escape(state, quote=True)}">
    <input type="hidden" name="code_challenge" value="{html.escape(code_challenge, quote=True)}">
    <input type="hidden" name="code_challenge_method" value="{html.escape(code_challenge_method, quote=True)}">
    <input type="password" name="secret" placeholder="Clave de acceso MCP" autocomplete="current-password" required autofocus>
    <button type="submit">Autorizar acceso</button>
  </form>
</div></body></html>"""


def build_protected_http_app(mcp, server_label: str, subtitle: str):
    mcp_asgi = mcp.streamable_http_app()

    class ProtectedOAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            base = _base_url(request)
            auth_secret = os.getenv("MCP_AUTH_SECRET", "").strip()

            if path == "/health":
                return JSONResponse({"status": "ok", "server": server_label})

            if path == "/.well-known/oauth-authorization-server":
                return JSONResponse({
                    "issuer": base,
                    "authorization_endpoint": f"{base}/oauth/authorize",
                    "token_endpoint": f"{base}/oauth/token",
                    "registration_endpoint": f"{base}/oauth/register",
                    "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code", "refresh_token"],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
                })

            if path == "/.well-known/oauth-protected-resource":
                return JSONResponse({
                    "resource": f"{base}/mcp",
                    "authorization_servers": [base],
                    "bearer_methods_supported": ["header"],
                })

            if path == "/oauth/register":
                try:
                    body = await request.json()
                except Exception:
                    body = {}
                return JSONResponse({
                    "client_id": str(uuid.uuid4()),
                    "client_secret": str(uuid.uuid4()),
                    "redirect_uris": body.get("redirect_uris", []),
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": body.get(
                        "token_endpoint_auth_method", "client_secret_post"
                    ),
                }, status_code=201)

            if not auth_secret:
                return JSONResponse(
                    {"error": "MCP_AUTH_SECRET no configurado en el servidor"},
                    status_code=503,
                )

            if path == "/oauth/authorize":
                if request.method == "GET":
                    p = request.query_params
                    redirect_uri = p.get("redirect_uri", "")
                    if not _valid_redirect_uri(redirect_uri):
                        return JSONResponse({"error": "redirect_uri invalida"}, status_code=400)
                    return HTMLResponse(
                        _render_authorize_html(
                            title=f"Autorizar {server_label}",
                            subtitle=subtitle,
                            redirect_uri=redirect_uri,
                            state=p.get("state", ""),
                            code_challenge=p.get("code_challenge", ""),
                            code_challenge_method=p.get("code_challenge_method", ""),
                        )
                    )

                form = await request.form()
                redirect_uri = str(form.get("redirect_uri", ""))
                state = str(form.get("state", ""))
                code_challenge = str(form.get("code_challenge", ""))
                code_challenge_method = str(form.get("code_challenge_method", ""))
                submitted_secret = str(form.get("secret", ""))

                if not _valid_redirect_uri(redirect_uri):
                    return JSONResponse({"error": "redirect_uri invalida"}, status_code=400)

                if not hmac.compare_digest(submitted_secret, auth_secret):
                    return HTMLResponse(
                        _render_authorize_html(
                            title=f"Autorizar {server_label}",
                            subtitle=subtitle,
                            redirect_uri=redirect_uri,
                            state=state,
                            code_challenge=code_challenge,
                            code_challenge_method=code_challenge_method,
                            error="Clave incorrecta. Intenta de nuevo.",
                        ),
                        status_code=403,
                    )

                code = _sign_token(
                    auth_secret,
                    {
                        "typ": "code",
                        "exp": int(time.time()) + 300,
                        "cc": code_challenge,
                        "ccm": code_challenge_method,
                    },
                )
                sep = "&" if "?" in redirect_uri else "?"
                target = f"{redirect_uri}{sep}code={code}"
                if state:
                    target += f"&state={state}"
                return RedirectResponse(target, status_code=302)

            if path == "/oauth/token":
                ct = request.headers.get("content-type", "")
                if "application/json" in ct:
                    data = await request.json()
                else:
                    body_bytes = await request.body()
                    parsed = parse_qs(body_bytes.decode("utf-8"))
                    data = {k: v[0] for k, v in parsed.items() if v}

                grant_type = data.get("grant_type", "authorization_code")
                now = int(time.time())

                if grant_type == "refresh_token":
                    rt = _verify_token(auth_secret, str(data.get("refresh_token", "")))
                    if not rt or rt.get("typ") != "refresh":
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)
                else:
                    code_payload = _verify_token(auth_secret, str(data.get("code", "")))
                    if not code_payload or code_payload.get("typ") != "code":
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)
                    cc = code_payload.get("cc", "")
                    ccm = code_payload.get("ccm", "")
                    if cc:
                        verifier = str(data.get("code_verifier", ""))
                        if not verifier:
                            return JSONResponse({"error": "invalid_grant"}, status_code=400)
                        if ccm == "S256":
                            computed = _b64url_encode(
                                hashlib.sha256(verifier.encode("ascii")).digest()
                            )
                            if not hmac.compare_digest(computed, cc):
                                return JSONResponse({"error": "invalid_grant"}, status_code=400)

                access_token = _sign_token(
                    auth_secret, {"typ": "access", "exp": now + 31536000}
                )
                refresh_token = _sign_token(
                    auth_secret, {"typ": "refresh", "exp": now + 63072000}
                )
                return JSONResponse({
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer",
                    "expires_in": 31536000,
                })

            if request.method == "OPTIONS":
                return await call_next(request)

            auth_header = request.headers.get("authorization", "")
            bearer = ""
            if auth_header.lower().startswith("bearer "):
                bearer = auth_header[7:].strip()

            token_ok = False
            if bearer:
                if hmac.compare_digest(bearer, auth_secret):
                    token_ok = True
                else:
                    payload = _verify_token(auth_secret, bearer)
                    token_ok = bool(payload and payload.get("typ") == "access")

            if not token_ok:
                return JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={
                        "WWW-Authenticate": f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource"'
                    },
                )

            return await call_next(request)

    app = ProtectedOAuthMiddleware(mcp_asgi)
    app = CORSMiddleware(app, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    return app
