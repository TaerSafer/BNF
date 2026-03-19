"""
Registre de composants d'O.R.I.O.N.

Gère l'enregistrement, la découverte et le cycle de vie
de tous les moteurs et modules du système.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("orion.registry")


class ComponentRegistry:
    """Registre central des composants O.R.I.O.N."""

    def __init__(self) -> None:
        self._components: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(self, name: str, component: Any, **metadata: Any) -> None:
        """Enregistre un composant dans le registre."""
        if name in self._components:
            logger.warning("Composant '%s' déjà enregistré, remplacement", name)
        self._components[name] = component
        self._metadata[name] = metadata
        logger.info("Composant enregistré: %s", name)

    def get(self, name: str) -> Any:
        """Récupère un composant par son nom."""
        if name not in self._components:
            raise KeyError(f"Composant '{name}' non trouvé dans le registre")
        return self._components[name]

    def has(self, name: str) -> bool:
        """Vérifie si un composant existe."""
        return name in self._components

    def unregister(self, name: str) -> None:
        """Retire un composant du registre."""
        self._components.pop(name, None)
        self._metadata.pop(name, None)

    def list_components(self) -> list[str]:
        """Liste tous les composants enregistrés."""
        return list(self._components.keys())

    def get_metadata(self, name: str) -> dict[str, Any]:
        """Retourne les métadonnées d'un composant."""
        return self._metadata.get(name, {})
