"""Export to Excel and CSV [NFR-03]. Implemented in phase 6."""

from __future__ import annotations

from pmtool.services._base import ServiceBase


class ExportService(ServiceBase):
    def to_excel(self) -> bytes:
        raise NotImplementedError("Export arrives in phase 6 (architecture §12).")

    def to_csv_zip(self) -> bytes:
        raise NotImplementedError("Export arrives in phase 6 (architecture §12).")
