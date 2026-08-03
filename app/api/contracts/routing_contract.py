"""Routing endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register routing models with the API namespace."""

    coordinate = api.model(
        "RouteCoordinate",
        {
            "latitude": fields.Float(description="Latitude"),
            "longitude": fields.Float(description="Longitude"),
        },
    )

    route_response = api.model(
        "RouteResponse",
        {
            "coordinates": fields.List(
                fields.Nested(coordinate),
                description="Polyline ordenada do ponto de origem ao destino",
            ),
            "distance_meters": fields.Float(description="Distância total em metros"),
            "duration_seconds": fields.Float(description="Duração estimada em segundos"),
        },
    )

    return {
        "coordinate": coordinate,
        "route_response": route_response,
    }
