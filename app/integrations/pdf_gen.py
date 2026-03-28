import os
import uuid
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader

logger = structlog.get_logger()

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "pdf"
TMP_DIR = Path("/tmp/pdf")

env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


class PDFGenerator:
    """Generate PDF from artifact data using Jinja2 + WeasyPrint."""

    async def generate(self, artifact_type: str, data: dict, run_id: uuid.UUID) -> Path | None:
        try:
            template = env.get_template(f"{artifact_type}.html")
            html = template.render(**data)

            TMP_DIR.mkdir(parents=True, exist_ok=True)
            output_path = TMP_DIR / f"{run_id}.pdf"

            from weasyprint import HTML
            HTML(string=html).write_pdf(str(output_path))

            return output_path
        except Exception as e:
            logger.error("pdf_gen_error", artifact_type=artifact_type, error=str(e))
            return None

    @staticmethod
    def cleanup(path: Path) -> None:
        try:
            os.remove(path)
        except OSError:
            pass


pdf_gen = PDFGenerator()
