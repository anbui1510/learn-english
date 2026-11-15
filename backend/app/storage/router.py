from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.storage.factory import get_storage
from app.storage.local import LocalFilesystemStorage

router = APIRouter(tags=["storage"])


@router.get("/storage/local")
def download_local_signed(
    key: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
) -> Response:
    """Serve a locally stored object when the HMAC signed URL is valid."""
    storage = get_storage()
    if not isinstance(storage, LocalFilesystemStorage):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local signed URLs are unavailable",
        )
    if not storage.verify_signature(key, exp, sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired download signature",
        )
    if not storage.exists(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found")
    data = storage.get(key)
    return Response(
        content=data,
        media_type=storage.content_type(key),
        headers={"Content-Disposition": f'inline; filename="{key.split("/")[-1]}"'},
    )
