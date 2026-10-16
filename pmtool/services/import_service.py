"""CSV import [NFR-08]. Implemented in phase 6."""

from __future__ import annotations

from pmtool.services._base import ServiceBase


class ImportService(ServiceBase):
    def from_csv(self, content: bytes):  # -> ImportResult (phase 6)
        raise NotImplementedError("Import arrives in phase 6 (architecture §12).")
