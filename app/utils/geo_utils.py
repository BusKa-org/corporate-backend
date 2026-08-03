"""Geospatial utility functions for calculating distances and coordinate math."""

import math


def calcular_distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula a distância em metros entre duas coordenadas geográficas (Fórmula de Haversine)."""
    R = 6371000
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
