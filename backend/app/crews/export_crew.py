"""
crews/export_crew.py
────────────────────
Pure-Python crew that renders the final report into HTML + DOCX and uploads
both to MinIO. Sits between ``report_generator`` and ``report_verifier`` in
the Automation Testing API DAG.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback

logger = logging.getLogger(__name__)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ExportCrew(BaseCrew):
    """Render HTML + DOCX + PDF and upload them to MinIO."""

    stage = "reporting"
    agent_ids: list[str] = ["export_html_docx"]

    def __init__(
        self,
        run_id: str,
        run_profile_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        **_kwargs: Any,
    ) -> None:
        super().__init__(
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Export the report and forward storage paths downstream."""
        self._emit_agent_started("export_html_docx", "Report Export")

        try:
            html_bytes, docx_bytes, pdf_bytes = self._run_async_from_thread(
                self._export_bytes(),
                timeout=180,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[ExportCrew][%s] Export failed: %s", self._run_id, exc
            )
            self._emit_agent_failed("export_html_docx", str(exc))
            return {
                "export_ok": False,
                "html_bytes_size": 0,
                "docx_bytes_size": 0,
                "pdf_bytes_size": 0,
                "html_path": "",
                "docx_path": "",
                "pdf_path": "",
                "error": str(exc),
                **input_data,
            }

        paths: dict[str, str] = {}
        try:
            from app.services.storage_service import storage

            paths = storage.upload_report(
                self._run_id,
                html_bytes=html_bytes,
                docx_bytes=docx_bytes,
                pdf_bytes=pdf_bytes,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ExportCrew][%s] MinIO upload failed (continuing with bytes only): %s",
                self._run_id,
                exc,
            )
            self._emit_log(
                f"Report upload to MinIO failed: {exc}",
                level="warning",
            )

        self._emit_agent_completed(
            "export_html_docx",
            output_preview=(
                f"html={len(html_bytes):,}B docx={len(docx_bytes):,}B "
                f"pdf={len(pdf_bytes):,}B paths={paths}"
            ),
        )

        out = dict(input_data)
        out.update(
            {
                "export_ok": True,
                "html_bytes_size": len(html_bytes),
                "docx_bytes_size": len(docx_bytes),
                "pdf_bytes_size": len(pdf_bytes),
                "html_path": paths.get("html", ""),
                "docx_path": paths.get("docx", ""),
                "pdf_path": paths.get("pdf", ""),
                # Checksums persisted for integrity / verification reporting.
                "report_checksums": {
                    "html": _sha256(html_bytes),
                    "docx": _sha256(docx_bytes),
                    "pdf": _sha256(pdf_bytes),
                },
                # Bytes carried through for in-process tests + verifier checks.
                "_html_bytes": html_bytes,
                "_docx_bytes": docx_bytes,
                "_pdf_bytes": pdf_bytes,
            }
        )
        return out

    async def _export_bytes(self) -> tuple[bytes, bytes, bytes]:
        from app.services.export_service import ExportService

        service = ExportService(self._run_id)
        html_bytes = await service.export_html()
        docx_bytes = await service.export_docx()
        pdf_bytes = await service.export_pdf()
        return html_bytes, docx_bytes, pdf_bytes
