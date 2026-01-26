import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from supabase_db import get_client, utc_now_iso

load_dotenv()

app = FastAPI(
    title="Kenbot API",
    version="1.0.0",
    description="Kenbot API (enqueue only). Runner executes via cron.",
)

SB = None

def sb():
    global SB
    if SB is None:
        SB = get_client()  # lit SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
    return SB


class BasicReply(BaseModel):
    ok: bool
    message: str
    data: Dict[str, Any] = {}


class RunOptions(BaseModel):
    dry_run: Optional[bool] = None
    max_targets: Optional[int] = None
    force_stock: Optional[str] = None
    rebuild_posts: Optional[bool] = None
    rebuild_limit: Optional[int] = None


@app.get("/health", response_model=BasicReply)
def health():
    return BasicReply(ok=True, message="OK", data={"service": "kenbot-api"})


@app.get("/config", response_model=BasicReply)
def config():
    keys = [
        "KENBOT_BASE_URL", "KENBOT_INVENTORY_PATH", "KENBOT_TEXT_ENGINE_URL",
        "SB_BUCKET_OUTPUTS", "SB_BUCKET_RAW", "SB_BUCKET_STICKERS",
        "SUPABASE_URL",
    ]
    data = {k: os.getenv(k) for k in keys}
    return BasicReply(ok=True, message="config", data=data)


@app.post("/trigger/run", response_model=BasicReply)
def trigger_run(opt: RunOptions = RunOptions()):
    """
    Enqueue une demande de run. Le runner (cron) la verra et appliquera les options.
    """
    payload = opt.model_dump()
    payload["ts"] = utc_now_iso()

    # insert event
    try:
        r = sb().table("events").insert({
            "slug": "BOOT",
            "type": "RUN_REQUESTED",
            "payload": payload,
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return BasicReply(ok=True, message="run requested", data={"payload": payload})
