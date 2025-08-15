import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from src.api.routers import auth as auth_router
from src.api.routers import prescriptions as prescriptions_router
from src.core.config import get_settings

settings = get_settings()

# Basic logging configuration to ensure stack traces are emitted
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("med_backend")
logger.info("Starting Medical Prescription Backend")

openapi_tags = [
    {
        "name": "Health",
        "description": "Health check endpoints and basic info",
    },
    {
        "name": "Authentication",
        "description": "User registration, login (JWT), and user info",
    },
    {
        "name": "Prescriptions",
        "description": "Create, list, retrieve, and verify medical prescriptions",
    },
]

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    openapi_tags=openapi_tags,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"], summary="Health Check")
# PUBLIC_INTERFACE
def health_check():
    """Return basic health response for service availability checks."""
    return {"message": "Healthy"}


# Include routers
app.include_router(auth_router.router)
app.include_router(prescriptions_router.router)


@app.exception_handler(RequestValidationError)
# PUBLIC_INTERFACE
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Global handler to return HTTP 400 for request validation errors instead of 422.

    Args:
        request: The incoming request object.
        exc: The FastAPI RequestValidationError instance.

    Returns:
        JSONResponse with status 400, a high-level 'detail' message and an 'errors' array
        providing field-level validation issues.

    Notes:
        - This handler avoids exposing internal details while giving clients actionable feedback.
        - For 500-level errors elsewhere, stack traces are logged via logger.exception.
    """
    # Log as a warning without stack trace (client-side input issue)
    logger.warning("Validation error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Invalid request. Please correct the input and try again.",
            "errors": exc.errors(),
        },
    )
