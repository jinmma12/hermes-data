"""Recipe (instance version) management engine."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vessel.domain.models.instance import (
    AlgorithmInstance,
    AlgorithmInstanceVersion,
    CollectorInstance,
    CollectorInstanceVersion,
    TransferInstance,
    TransferInstanceVersion,
)

logger = logging.getLogger(__name__)

# Map instance_type string to (InstanceModel, VersionModel)
_TYPE_MAP: dict[str, tuple[type, type]] = {
    "COLLECTOR": (CollectorInstance, CollectorInstanceVersion),
    "ALGORITHM": (AlgorithmInstance, AlgorithmInstanceVersion),
    "TRANSFER": (TransferInstance, TransferInstanceVersion),
}


@dataclass
class RecipeDiff:
    """Diff between two recipe versions."""

    version_id_1: uuid.UUID
    version_id_2: uuid.UUID
    version_no_1: int
    version_no_2: int
    added: dict[str, Any] = field(default_factory=dict)
    removed: dict[str, Any] = field(default_factory=dict)
    changed: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ConfigValidationResult:
    """Result of validating a config against a JSON schema."""

    valid: bool
    errors: list[str] = field(default_factory=list)


def _get_models(instance_type: str) -> tuple[type, type]:
    key = instance_type.upper()
    if key not in _TYPE_MAP:
        raise ValueError(f"Unknown instance_type '{instance_type}'. Must be one of {list(_TYPE_MAP.keys())}")
    return _TYPE_MAP[key]


class RecipeEngine:
    """Manages versioned configuration (recipes) for instances."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_recipe(
        self,
        instance_type: str,
        instance_id: uuid.UUID,
        config_json: dict[str, Any],
        change_note: str | None = None,
        created_by: str | None = None,
    ) -> Any:
        """Create a new recipe version for an instance.

        Returns the newly created InstanceVersion model.
        """
        _inst_cls, ver_cls = _get_models(instance_type)

        # Determine next version number (use max version_no, not current recipe)
        _, ver_cls_for_max = _get_models(instance_type)
        max_stmt = (
            select(func.max(ver_cls_for_max.version_no))
            .where(ver_cls_for_max.instance_id == instance_id)
        )
        max_result = await self.db.execute(max_stmt)
        max_version = max_result.scalar() or 0
        next_version = max_version + 1

        current = await self.get_current_recipe(instance_type, instance_id)

        # Determine the def_version_id from instance or current recipe
        if current is not None:
            def_version_id = current.def_version_id
        else:
            instance = await self.db.get(_inst_cls, instance_id)
            if instance is None:
                raise ValueError(f"{instance_type} instance {instance_id} not found")
            # Use the latest def version from the definition
            from vessel.domain.models.definition import (
                AlgorithmDefinitionVersion,
                CollectorDefinitionVersion,
                TransferDefinitionVersion,
            )
            def_ver_map = {
                "COLLECTOR": CollectorDefinitionVersion,
                "ALGORITHM": AlgorithmDefinitionVersion,
                "TRANSFER": TransferDefinitionVersion,
            }
            def_ver_cls = def_ver_map[instance_type.upper()]
            stmt = (
                select(def_ver_cls)
                .where(def_ver_cls.definition_id == instance.definition_id)
                .order_by(def_ver_cls.version_no.desc())
                .limit(1)
            )
            result = await self.db.execute(stmt)
            def_version = result.scalar_one_or_none()
            if def_version is None:
                raise ValueError(
                    f"No definition version found for {instance_type} definition "
                    f"{instance.definition_id}"
                )
            def_version_id = def_version.id

        version = ver_cls(
            instance_id=instance_id,
            def_version_id=def_version_id,
            version_no=next_version,
            config_json=config_json,
            is_current=False,
            change_note=change_note,
            created_by=created_by,
        )
        self.db.add(version)
        await self.db.flush()
        logger.info(
            "Created recipe v%d for %s %s", next_version, instance_type, instance_id
        )
        return version

    async def get_current_recipe(
        self, instance_type: str, instance_id: uuid.UUID
    ) -> Any | None:
        """Get the current (published) recipe for an instance."""
        _, ver_cls = _get_models(instance_type)
        stmt = (
            select(ver_cls)
            .where(
                ver_cls.instance_id == instance_id,
                ver_cls.is_current == True,  # noqa: E712
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recipe_history(
        self, instance_type: str, instance_id: uuid.UUID
    ) -> list[Any]:
        """Get all recipe versions for an instance, ordered by version_no."""
        _, ver_cls = _get_models(instance_type)
        stmt = (
            select(ver_cls)
            .where(ver_cls.instance_id == instance_id)
            .order_by(ver_cls.version_no.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_recipe_by_version(
        self,
        instance_type: str,
        instance_id: uuid.UUID,
        version_no: int,
    ) -> Any | None:
        """Get a specific recipe version."""
        _, ver_cls = _get_models(instance_type)
        stmt = select(ver_cls).where(
            ver_cls.instance_id == instance_id,
            ver_cls.version_no == version_no,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def compare_recipes(
        self,
        instance_type: str,
        instance_id: uuid.UUID,
        version_no_1: int,
        version_no_2: int,
    ) -> RecipeDiff:
        """Compare two recipe versions and return the diff."""
        v1 = await self.get_recipe_by_version(instance_type, instance_id, version_no_1)
        v2 = await self.get_recipe_by_version(instance_type, instance_id, version_no_2)

        if v1 is None:
            raise ValueError(f"Version {version_no_1} not found")
        if v2 is None:
            raise ValueError(f"Version {version_no_2} not found")

        cfg1: dict[str, Any] = v1.config_json or {}
        cfg2: dict[str, Any] = v2.config_json or {}

        added = {k: cfg2[k] for k in cfg2 if k not in cfg1}
        removed = {k: cfg1[k] for k in cfg1 if k not in cfg2}
        changed = {}
        for k in cfg1:
            if k in cfg2 and cfg1[k] != cfg2[k]:
                changed[k] = {"from": cfg1[k], "to": cfg2[k]}

        return RecipeDiff(
            version_id_1=v1.id,
            version_id_2=v2.id,
            version_no_1=version_no_1,
            version_no_2=version_no_2,
            added=added,
            removed=removed,
            changed=changed,
        )

    async def publish_recipe(
        self, instance_type: str, instance_id: uuid.UUID, version_no: int
    ) -> Any:
        """Publish a recipe version, making it the current one.

        Un-publishes any previously current version.
        """
        _, ver_cls = _get_models(instance_type)

        # Un-publish existing current
        stmt = select(ver_cls).where(
            ver_cls.instance_id == instance_id,
            ver_cls.is_current == True,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        for existing in result.scalars().all():
            existing.is_current = False

        # Set the target version as current
        target = await self.get_recipe_by_version(instance_type, instance_id, version_no)
        if target is None:
            raise ValueError(f"Version {version_no} not found for {instance_type} {instance_id}")
        target.is_current = True
        await self.db.flush()
        logger.info(
            "Published recipe v%d for %s %s", version_no, instance_type, instance_id
        )
        return target

    def validate_config(
        self, config_json: dict[str, Any], input_schema: dict[str, Any]
    ) -> ConfigValidationResult:
        """Validate a config dict against a JSON Schema."""
        if not input_schema:
            return ConfigValidationResult(valid=True)

        validator = jsonschema.Draft7Validator(input_schema)
        errors = sorted(validator.iter_errors(config_json), key=lambda e: list(e.path))
        error_messages = [
            f"{'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
            for e in errors
        ]
        return ConfigValidationResult(
            valid=len(error_messages) == 0,
            errors=error_messages,
        )
