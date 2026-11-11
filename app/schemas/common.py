from typing import Any

from marshmallow import EXCLUDE, Schema, fields, pre_load
from marshmallow.validate import Range


class BaseSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    def _normalize(self, obj: Any) -> Any:
        if obj is None:
            return None

        if isinstance(obj, str):
            v = obj.strip()
            return v

        if isinstance(obj, list):
            return [self._normalize(x) for x in obj]

        if isinstance(obj, dict):
            return {k: self._normalize(v) for k, v in obj.items()}

        return obj

    @pre_load
    def normalize_input(self, data: Any, **kwargs: Any) -> Any:
        if data is None:
            return {}
        # only normalize dict/list payloads; let marshmallow complain otherwise
        if not isinstance(data, (dict, list)):
            return data
        return self._normalize(data)


class PaginacaoQuerySchema(BaseSchema):
    """Shared ?page=&per_page= query params."""

    page = fields.Integer(required=False, load_default=1, validate=Range(min=1))
    per_page = fields.Integer(required=False, load_default=20, validate=Range(min=1, max=100))
