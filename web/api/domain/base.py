"""Base class for domain models.

``extra="allow"`` keeps tolerance for fields older records or the firmware may
carry that aren't modelled explicitly. ``to_dict()`` / ``from_dict()`` are the
serialization seam used by both repository backends.
"""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=False)

    @classmethod
    def from_dict(cls, data: dict):
        return cls.model_validate(data)
