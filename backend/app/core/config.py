"""Application configuration loaded from environment / .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "AI-ARCTEG"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Database
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'arcteg.db'}"

    # Auth
    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    default_admin_email: str = "admin@arcteg.local"
    default_admin_password: str = "ChangeMe!123"

    # CORS / API
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    api_v1_prefix: str = "/api/v1"
    rate_limit_per_minute: int = 120

    # MQTT
    mqtt_broker_url: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_topic_prefix: str = "ai-arcteg"

    # Hardware ingestion
    device_ingest_api_key: str = "dev-ingest-key"
    hardware_online_threshold_seconds: int = 60

    # Simulation
    simulation_autostart: bool = True
    simulation_tick_seconds: float = 5.0
    simulation_speed: float = 1.0
    simulation_latitude: float = 23.8103
    simulation_longitude: float = 90.4125
    simulation_default_location: str = "Dhaka"

    # Physics model parameters
    pv_area_m2: float = 0.5
    concentrator_area_m2: float = 0.4
    pv_efficiency: float = 0.17
    teg_seebeck_v_per_k: float = 0.045
    teg_internal_resistance_ohm: float = 3.2
    concentrator_gain_k: float = 58.0

    # ML
    model_path: str = str(PROJECT_ROOT / "ml" / "models")
    model_autoload: bool = True

    # Weather provider
    weather_api_key: str = ""
    weather_api_provider: str = ""
    weather_api_base_url: str = ""

    # Paths
    data_dir: str = str(PROJECT_ROOT / "data")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
