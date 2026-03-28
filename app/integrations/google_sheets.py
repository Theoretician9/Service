import structlog

from app.config import settings

logger = structlog.get_logger()


class GoogleSheetsExporter:
    """Google Sheets export for artifacts (Paid only)."""

    def __init__(self):
        self._service = None

    async def export_to_existing(
        self, spreadsheet_url: str, data: list[list], sheet_name: str
    ) -> str:
        """Write data to existing spreadsheet. Returns sheet URL."""
        raise NotImplementedError

    async def create_and_export(
        self, title: str, data: list[list], share_email: str
    ) -> str:
        """Create new spreadsheet, write data, share with user. Returns URL."""
        raise NotImplementedError


google_sheets = GoogleSheetsExporter()
