"""图片代理 —— 绕过 CDN Referer 校验导致的 403。"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import httpx

router = APIRouter()

_client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)


@router.get("/proxy/image")
async def proxy_image(url: str = Query(...)):
    """代理获取远程图片，设置空 Referer 绕过防盗链。"""
    try:
        resp = await _client.get(url, headers={"Referer": ""})
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="获取图片失败")
        content_type = resp.headers.get("content-type", "image/png")
        return Response(content=resp.content, media_type=content_type)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))
