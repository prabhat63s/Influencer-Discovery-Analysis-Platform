from fastapi import Request
import time
import logging

logger = logging.getLogger("api.request")

async def request_logger(request: Request, call_next):
    """
    Middleware to log incoming requests and execution time.
    """
    start_time = time.time()
    
    # Log Request
    logger.info(f"Incoming Request: {request.method} {request.url}")
    
    response = await call_next(request)
    
    # Calculate duration
    process_time = (time.time() - start_time) * 1000
    
    # Log Response
    logger.info(
        f"Request Completed: {request.method} {request.url} "
        f"Status: {response.status_code} "
        f"Duration: {process_time:.2f}ms"
    )
    
    return response
