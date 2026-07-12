from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradecore.core.config import get_settings

app = FastAPI(title="Auto-Crypto Trader API", version="0.1.0")

# Enable CORS for frontend dashboard interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_endpoint() -> dict[str, str]:
    """
    Standard service health endpoint returning current mode.
    """
    return {"status": "ok", "mode": get_settings().trading.mode.value}
