"""Generate beautiful HTML report pages from artifact data."""
import os
import uuid
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader

logger = structlog.get_logger()

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "reports"
# Write to /app/reports inside container — mounted as volume to host
REPORTS_DIR = Path("/app/reports")

env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


class HTMLReportGenerator:
    """Generate static HTML report pages from artifact data."""

    async def generate(self, artifact_type: str, data: dict, run_id: str) -> str | None:
        """Generate HTML report and return its URL path (relative to /reports/)."""
        try:
            template = env.get_template(f"{artifact_type}.html")
            html = template.render(**data)

            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{run_id}.html"
            output_path = REPORTS_DIR / filename
            output_path.write_text(html, encoding="utf-8")

            return filename
        except Exception as e:
            logger.error("html_report_error", artifact_type=artifact_type, error=str(e))
            return None


html_report = HTMLReportGenerator()
