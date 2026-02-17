from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
import logging

router = APIRouter(
    prefix="/api/proxy",
    tags=["Utility"]
)

logger = logging.getLogger(__name__)

@router.get("/image")
async def proxy_image(url: str = Query(..., description="Target URL")):
    """
    Proxies an external image URL to bypass CORS restrictions.
    """
    if not url or not url.startswith("http"):
         raise HTTPException(status_code=400, detail="Invalid URL")

    # Create a client that will be closed after the response is sent
    client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    try:
        req = client.build_request("GET", url)
        r = await client.send(req, stream=True)
        
        if r.status_code != 200:
            await r.aclose()
            await client.aclose()
            logger.error(f"Failed to fetch proxy image: {url} status={r.status_code}")
            # Return a 404 image or raise exception
            raise HTTPException(status_code=404, detail="Image not found")
            
        return StreamingResponse(
            r.aiter_bytes(), 
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*"
            },
            background=client.aclose 
        )
    except Exception as e:
        await client.aclose()
        logger.error(f"Proxy error: {e}")
        raise HTTPException(status_code=500, detail="Proxy error")
