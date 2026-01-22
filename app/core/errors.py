from __future__ import annotations


class ExternalAPIError(RuntimeError):
    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.service = service
        self.status_code = status_code
