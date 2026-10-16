"""Live data package — OpenWeatherMap integration (primary data source)."""

from src.live.openweather import (                                  # noqa: F401
    CITIES,
    OpenWeatherError,
    fetch_current,
    fetch_forecast,
    latest,
    status,
    sync,
)
