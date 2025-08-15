from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import auth as auth_router
from src.api.routers import prescriptions as prescriptions_router
from src.core.config import get_settings

settings = get_settings()

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
