from typing import Any

from marshmallow import EXCLUDE, Schema, pre_load


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
