class CreatosConnectError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, code: str = "UNKNOWN", details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

class ScraperError(CreatosConnectError):
    """Raised when external scraping fails."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="SCRAPER_ERROR", details=details)

class ValidationError(CreatosConnectError):
    """Raised when input validation fails."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)

class PipelineError(CreatosConnectError):
    """Raised when pipeline orchestration fails."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="PIPELINE_ERROR", details=details)

class RateLimitError(CreatosConnectError):
    """Raised when API rate limits are exceeded."""
    def __init__(self, message: str = "Rate limit exceeded", details: dict = None):
        super().__init__(message, code="RATE_LIMIT_EXCEEDED", details=details)

class ResourceNotFoundError(CreatosConnectError):
    """Raised when a requested resource is not found."""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            f"{resource} with id {resource_id} not found", 
            code="RESOURCE_NOT_FOUND", 
            details={"resource": resource, "id": resource_id}
        )
