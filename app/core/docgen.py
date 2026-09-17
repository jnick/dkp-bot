from __future__ import annotations

import io
import os
import subprocess
import tempfile
from typing import Dict, Optional

from docxtpl import DocxTemplate

from app.config import DOCX_TEMPLATES_DIR


class DocGenerator:
    def render_docx(self, slug: str, context: Dict[str, str]) -> bytes:
        template_path = DOCX_TEMPLATES_DIR / f"{slug}.docx"
        if not template_path.exists():
            raise FileNotFoundError(f"Шаблон не найден: {template_path}")
        doc = DocxTemplate(str(template_path))
        doc.render(context)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    def render_pdf(self, docx_bytes: bytes, base_name: str) -> Optional[bytes]:
        """Конвертация DOCX -> PDF через headless LibreOffice."""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, f"{base_name}.docx")
            with open(src, "wb") as f:
                f.write(docx_bytes)
            try:
                result = subprocess.run(
                    ["soffice", "--headless", "--convert-to", "pdf", "--outdir", td, src],
                    capture_output=True,
                    timeout=180,
                )
            except FileNotFoundError:
                return None
            if result.returncode != 0:
                return None
            pdf_path = os.path.join(td, f"{base_name}.pdf")
            if not os.path.exists(pdf_path):
                return None
            with open(pdf_path, "rb") as f:
                return f.read()