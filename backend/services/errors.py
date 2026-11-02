"""One error shape for the whole API: {"error": {"code", "message", "job_id", "retryable"}}."""
from fastapi import Request
from fastapi.responses import JSONResponse

ERROR_STATUS = {
    "INPUT_INVALID": 422,
    "NOT_FOUND": 404,
    "FORBIDDEN": 403,
    "UNAUTHORIZED": 401,
    "NOT_APPROVED": 403,
    "INVALID_STATE": 409,
    "CONTEXT_INSUFFICIENT": 409,
    "UNSUPPORTED_CLAIMS": 409,
    "RETRIEVAL_FAILED": 503,
    "MODEL_FAILED": 502,
    "EXPORT_FAILED": 502,
}
RETRYABLE = {"RETRIEVAL_FAILED", "MODEL_FAILED", "EXPORT_FAILED"}


class AppError(Exception):
    def __init__(self, code: str, message: str, job_id: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.job_id = job_id
        self.details = details or {}

    @property
    def status(self) -> int:
        return ERROR_STATUS.get(self.code, 400)

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "job_id": self.job_id,
                          "retryable": self.code in RETRYABLE, **({"details": self.details} if self.details else {})}}


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.body())
