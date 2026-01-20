from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import runner  # ton runner.py


app = FastAPI(
    title="Kenbot Runner API",
    version="1.0.0",
    description="API Kenbot (Scrape Kennebec + Supabase + Facebook + RAW audit + SOLD/RESTORE).",
)

# -------------------------
# Models
# -------------------------
class RunOptions(BaseModel):
    dry_run: Optional[bool] = None
    max_targets: Optional[int] = None
    force_stock: Optional[str] = None
    rebuild_posts: Optional[bool] = None
    rebuild_limit: Optional[int] = None


class BasicReply(BaseModel):
    ok: bool
    message: str
    data: Dict[str, Any] = {}


# -------------------------
# Helpers
# -------------------------
def _set_env_bool(key: str, value: Optional[bool]) -> None:
    if value is None:
        return
    os.environ[key] = "1" if value else "0"


def _set_env_int(key: str, value: Optional[int]) -> None:
    if value is None:
        return
    os.environ[key] = str(value)


def _set_env_str(key: str, value: Optional[str]) -> None:
    if value is None:
        return
    os.environ[key] = value


def _apply_options(opt: RunOptions) -> None:
    _set_env_bool("KENBOT_DRY_RUN", opt.dry_run)
    _set_env_int("KENBOT_MAX_TARGETS", opt.max_targets)
    _set_env_str("KENBOT_FORCE_STOCK", (opt.force_stock or "").strip().upper() if opt.force_stock else None)
    _set_env_bool("KENBOT_REBUILD_POSTS", opt.rebuild_posts)
    _set_env_int("KENBOT_REBUILD_LIMIT", opt.rebuild_limit)


def _guard(msg: str) -> None:
    raise HTTPException(status_code=400, detail=msg)


# -------------------------
# 19 Endpoints (style "menu")
# -------------------------

@app.get("/health", response_model=BasicReply)
def health():
    return BasicReply(ok=True, message="OK", data={"service": "kenbot-runner-api"})


@app.get("/config", response_model=BasicReply)
def config():
    keys = [
        "KENBOT_BASE_URL",
        "KENBOT_INVENTORY_PATH",
        "KENBOT_TEXT_ENGINE_URL",
        "KENBOT_DRY_RUN",
        "KENBOT_FORCE_STOCK",
        "KENBOT_MAX_TARGETS",
        "KENBOT_REBUILD_POSTS",
        "KENBOT_REBUILD_LIMIT",
        "SB_BUCKET_RAW",
        "SB_BUCKET_STICKERS",
        "SB_BUCKET_OUTPUTS",
        "SUPABASE_URL",
    ]
    data = {k: os.getenv(k) for k in keys}
    return BasicReply(ok=True, message="config", data=data)


@app.post("/run", response_model=BasicReply)
def run_all(opt: RunOptions = RunOptions()):
    """
    Run complet: rebuild (optionnel), scrape 3 pages, upsert inventory, SOLD/RESTORE, NEW/PRICE_CHANGED, stickers cache.
    """
    _apply_options(opt)
    try:
        runner.main()
    except SystemExit as e:
        _guard(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="run done", data={})


@app.post("/rebuild/posts", response_model=BasicReply)
def rebuild_posts(limit: int = 300):
    """
    Rebuild mémoire FB -> Supabase (posts.post_id), sans faire le reste.
    """
    os.environ["KENBOT_REBUILD_POSTS"] = "1"
    os.environ["KENBOT_REBUILD_LIMIT"] = str(limit)
    try:
        # On réutilise runner.main() mais en mode rebuild-only (tu peux garder ça simple)
        runner.main()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="rebuild posts done", data={"limit": limit})


@app.post("/scrape/pages", response_model=BasicReply)
def scrape_pages():
    """
    Scrape listing pages (3 pages) et retourne le nombre d'URLs trouvées.
    """
    try:
        urls, pages_html = runner._fetch_listing_pages_for_api()  # à ajouter (voir note plus bas)
    except AttributeError:
        _guard("Ajoute runner._fetch_listing_pages_for_api() (helper API) ou utilise /run.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return BasicReply(ok=True, message="scrape pages ok", data={"count_urls": len(urls), "pages": len(pages_html)})


@app.post("/raw/upload", response_model=BasicReply)
def raw_upload():
    """
    Force upload RAW des 3 pages (audit).
    """
    try:
        out = runner._upload_raw_for_api()  # à ajouter
    except AttributeError:
        _guard("Ajoute runner._upload_raw_for_api() ou définis upload_raw_pages() + appelle-la dans /run.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="raw upload ok", data=out)


@app.post("/inventory/upsert", response_model=BasicReply)
def inventory_upsert():
    """
    Force upsert inventory (ACTIVE) à partir du scrape courant.
    """
    try:
        out = runner._upsert_inventory_for_api()  # à ajouter
    except AttributeError:
        _guard("Ajoute runner._upsert_inventory_for_api() ou utilise /run.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="inventory upsert ok", data=out)


@app.post("/sold/process", response_model=BasicReply)
def process_sold():
    """
    Applique SOLD: ajoute bandeau VENDU au post FB sans détruire base_text.
    """
    try:
        out = runner._process_sold_for_api()  # à ajouter
    except AttributeError:
        _guard("Ajoute runner._process_sold_for_api() ou utilise /run.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="sold processed", data=out)


@app.post("/restore/process", response_model=BasicReply)
def process_restore():
    """
    Restore si vendu par erreur: retire bandeau et remet base_text.
    """
    try:
        out = runner._process_restore_for_api()  # à ajouter
    except AttributeError:
        _guard("Ajoute runner._process_restore_for_api() ou utilise /run.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="restore processed", data=out)


@app.post("/price_changed/process", response_model=BasicReply)
def process_price_changed():
    """
    Applique PRICE_CHANGED: update texte FB sur post existant.
    """
    try:
        out = runner._process_price_changed_for_api()  # à ajouter
    except AttributeError:
        _guard("Ajoute runner._process_price_changed_for_api() ou utilise /run.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="price_changed processed", data=out)


@app.post("/new/publish", response_model=BasicReply)
def publish_new():
    """
    Publie les NEW (avec photos), selon MAX_TARGETS.
    """
    try:
        out = runner._publish_new_for_api()  # à ajouter
    except AttributeError:
        _guard("Ajoute runner._publish_new_for_api() ou utilise /run.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="new published", data=out)


@app.post("/force/stock", response_model=BasicReply)
def force_stock(stock: str, dry_run: bool = False):
    """
    Force un stock précis (test visuel).
    """
    if not stock:
        _guard("stock requis")
    os.environ["KENBOT_FORCE_STOCK"] = stock.strip().upper()
    os.environ["KENBOT_DRY_RUN"] = "1" if dry_run else "0"
    try:
        runner.main()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="force stock done", data={"stock": stock, "dry_run": dry_run})


@app.post("/stickers/cache_one", response_model=BasicReply)
def cache_one_sticker(vin: str):
    """
    Cache un window sticker Stellantis (PDF) en storage.
    """
    if not vin or len(vin.strip()) != 17:
        _guard("VIN invalide")
    try:
        sb = runner.get_client(runner.SUPABASE_URL, runner.SUPABASE_KEY)
        meta = runner.ensure_sticker_cached(sb, vin.strip().upper(), run_id="api")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="sticker cached", data=meta)


@app.post("/facebook/update_text", response_model=BasicReply)
def fb_update_text(post_id: str, text: str):
    """
    Update texte FB brut (debug).
    """
    if not post_id or not text:
        _guard("post_id et text requis")
    try:
        runner.update_post_text(post_id, runner.FB_TOKEN, text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="fb text updated", data={"post_id": post_id})


@app.get("/posts/sample", response_model=BasicReply)
def posts_sample(limit: int = 10):
    """
    Retourne un échantillon posts map (debug).
    """
    try:
        sb = runner.get_client(runner.SUPABASE_URL, runner.SUPABASE_KEY)
        posts = runner.get_posts_map(sb)
        items = list(posts.items())[: max(1, min(limit, 50))]
        data = {k: v for k, v in items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="posts sample", data=data)


@app.get("/inventory/sample", response_model=BasicReply)
def inventory_sample(limit: int = 10):
    """
    Retourne un échantillon inventory map (debug).
    """
    try:
        sb = runner.get_client(runner.SUPABASE_URL, runner.SUPABASE_KEY)
        inv = runner.get_inventory_map(sb)
        items = list(inv.items())[: max(1, min(limit, 50))]
        data = {k: v for k, v in items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="inventory sample", data=data)


@app.post("/maintenance/rebuild_then_run", response_model=BasicReply)
def rebuild_then_run(limit: int = 300, max_targets: int = 6):
    """
    Mode "ancien Kenbot": rebuild FB mapping puis run complet.
    """
    os.environ["KENBOT_REBUILD_POSTS"] = "1"
    os.environ["KENBOT_REBUILD_LIMIT"] = str(limit)
    os.environ["KENBOT_MAX_TARGETS"] = str(max_targets)
    try:
        runner.main()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return BasicReply(ok=True, message="rebuild+run done", data={"limit": limit, "max_targets": max_targets})


@app.post("/maintenance/disable_rebuild", response_model=BasicReply)
def disable_rebuild():
    """
    Remet KENBOT_REBUILD_POSTS=0 (mode normal).
    """
    os.environ["KENBOT_REBUILD_POSTS"] = "0"
    return BasicReply(ok=True, message="rebuild disabled", data={})


@app.get("/version", response_model=BasicReply)
def version():
    return BasicReply(ok=True, message="version", data={"api": "1.0.0"})
