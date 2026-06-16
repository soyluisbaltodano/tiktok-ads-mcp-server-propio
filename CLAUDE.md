# mcp-tiktok-ads

Servidor MCP local para la TikTok Marketing API v1.3.
Permite consultar campañas, ad groups, anuncios y reportes desde Claude Code
sin exponer las credenciales en la conversación.

## Estructura

```
mcp-tiktok-ads/
├── server.py          # Servidor MCP (punto de entrada)
├── tiktok/
│   └── client.py      # Llamadas directas a la API de TikTok
├── .env               # Credenciales (nunca subir a git)
├── .gitignore
└── requirements.txt
```

## Setup inicial

```powershell
cd C:\Users\balto\proyectos-claude\mcp-tiktok-ads
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Credenciales (.env)

| Variable | Dónde obtenerla |
|---|---|
| TIKTOK_APP_ID | TikTok for Business → Apps |
| TIKTOK_APP_SECRET | TikTok for Business → Apps |
| TIKTOK_ACCESS_TOKEN | OAuth flow o modo sandbox |
| TIKTOK_ADVERTISER_ID | Panel de TikTok Ads → URL de la cuenta |

## Arrancar el servidor

```powershell
python server.py
```

## Registrar en Claude Code

Agrega esto a tu `claude_desktop_config.json` o al settings de Claude Code:

```json
{
  "mcpServers": {
    "tiktok-ads": {
      "command": "python",
      "args": ["C:/Users/balto/proyectos-claude/mcp-tiktok-ads/server.py"]
    }
  }
}
```

## Herramientas disponibles

| Tool | Descripción |
|---|---|
| `get_advertiser_info` | Info de la cuenta (nombre, balance, moneda) |
| `get_campaigns` | Lista campañas, filtrable por estado |
| `get_adgroups` | Lista ad groups, filtrable por campaña |
| `get_ads` | Lista anuncios, filtrable por ad group |
| `get_report` | Reporte de rendimiento por rango de fechas |
