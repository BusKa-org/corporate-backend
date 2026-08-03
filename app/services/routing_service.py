"""Routing service - OSRM driving-route proxy.

Centralises all outbound OSRM calls so the frontend never contacts
the tile/routing infrastructure directly, and every request carries
the proper identification headers required by OSM's usage policy.
"""

import logging
from typing import Any

import requests
from requests.exceptions import ConnectionError, Timeout

from app.core.exceptions import AppError, ValidationError

logger = logging.getLogger(__name__)

_OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"
_USER_AGENT = "BusKa/1.0 (school-transport management; https://github.com/buska)"
_TIMEOUT_SECONDS = 10


def get_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict[str, Any]:
    """Fetch a driving route from OSRM and return a simplified polyline.

    Returns:
        {
            "coordinates": [{"latitude": float, "longitude": float}, ...],
            "distance_meters": float | None,
            "duration_seconds": float | None,
        }

    Raises:
        ValidationError: coordinates are out of the valid geographic range.
        AppError (503):  OSRM is unreachable or timed out.
        AppError (502):  OSRM returned an unexpected HTTP error.
        AppError (404):  OSRM found no route between the given points.
    """
    _validate_coordinates(origin_lat, origin_lng, dest_lat, dest_lng)

    coords_segment = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    url = f"{_OSRM_BASE_URL}/{coords_segment}"

    logger.debug(
        "Requesting OSRM route",
        extra={"origin": [origin_lat, origin_lng], "dest": [dest_lat, dest_lng]},
    )

    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Timeout:
        logger.warning("OSRM request timed out", extra={"url": url})
        raise AppError("Serviço de roteamento indisponível (timeout)", 503, "ROUTING_TIMEOUT")
    except ConnectionError:
        logger.warning("OSRM connection error", extra={"url": url})
        raise AppError("Serviço de roteamento indisponível", 503, "ROUTING_UNAVAILABLE")
    except requests.HTTPError as exc:
        logger.warning(
            "OSRM returned HTTP error",
            extra={"status": exc.response.status_code, "url": url},
        )
        raise AppError("Serviço de roteamento retornou erro inesperado", 502, "ROUTING_ERROR")

    data = response.json()
    route = (data.get("routes") or [None])[0]

    if not route:
        raise AppError("Nenhuma rota encontrada entre os pontos informados", 404, "NO_ROUTE_FOUND")

    # GeoJSON coordinates are [longitude, latitude]; we invert to {latitude, longitude}.
    raw_coords: list[list[float]] = route.get("geometry", {}).get("coordinates", [])
    coordinates = [{"latitude": lat, "longitude": lng} for lng, lat in raw_coords]

    return {
        "coordinates": coordinates,
        "distance_meters": route.get("distance"),
        "duration_seconds": route.get("duration"),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_coordinates(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> None:
    """Raise ValidationError if any coordinate is outside its geographic bounds."""
    checks = [
        ("origin_lat", origin_lat, -90.0, 90.0),
        ("dest_lat", dest_lat, -90.0, 90.0),
        ("origin_lng", origin_lng, -180.0, 180.0),
        ("dest_lng", dest_lng, -180.0, 180.0),
    ]
    for name, value, lo, hi in checks:
        if not (lo <= value <= hi):
            raise ValidationError(f"Coordenada inválida: {name}={value} (esperado [{lo}, {hi}])")
