import os
from functools import lru_cache
from typing import List

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


class Settings:
    """
    Application settings loaded from environment variables.

    - SQLITE_DB: Path to the SQLite DB file. Defaults to sibling database container's myapp.db.
    - MED_API_SECRET_KEY: Secret for signing JWT tokens.
    - MED_API_ALGORITHM: JWT algorithm (default HS256).
    - MED_API_ACCESS_TOKEN_EXPIRE_MINUTES: JWT expiration minutes (default 60).
    - CORS_ALLOW_ORIGINS: Comma-separated list of allowed origins for CORS.
    - SOLANA_NETWORK: solana network identifier: mainnet-beta, devnet, testnet, localnet
    """

    def __init__(self) -> None:
        # Compute default DB path to sibling database container
        default_db_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "../../myapp.db",
            )
        )

        # Database
        self.SQLITE_DB: str = os.getenv("SQLITE_DB", default_db_path)

        # Security
        self.MED_API_SECRET_KEY: str = os.getenv("MED_API_SECRET_KEY", "CHANGE_ME_IN_PROD")
        self.MED_API_ALGORITHM: str = os.getenv("MED_API_ALGORITHM", "HS256")
        self.MED_API_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("MED_API_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
        )

        # CORS
        cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*")
        if cors_origins_env.strip() == "*":
            self.CORS_ALLOW_ORIGINS: List[str] = ["*"]
        else:
            self.CORS_ALLOW_ORIGINS = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

        # Solana integration network (stubbed)
        self.SOLANA_NETWORK: str = os.getenv("SOLANA_NETWORK", "devnet")

        # API metadata
        self.APP_TITLE: str = os.getenv("APP_TITLE", "Medical Prescription Backend")
        self.APP_DESCRIPTION: str = os.getenv(
            "APP_DESCRIPTION",
            "Backend API for creating and verifying medical prescriptions with Solana integration (stub).",
        )
        self.APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")


# PUBLIC_INTERFACE
@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance for accessing application configuration."""
    return Settings()
