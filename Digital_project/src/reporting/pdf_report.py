"""Court-ready forensic PDF report (ReportLab)."""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image as RLImage, KeepTogether,
)

from ..core.anomaly_detector import Anomaly
from ..core.exif_extractor import ExifData
from ..core.hasher import hash_string
from ..utils.constants import APP_NAME, APP_VERSION


SEVERITY_FILL = {
    "critical": colors.HexColor("#8B0000"),
    "high": colors.HexColor("#D32F2F"),
    "medium": colors.HexColor("#F57C00"),
    "low": colors.HexColor("#1976D2"),
    "info": colors.HexColor("#616161"),
}


@dataclass
class ReportContext:
    case_name: str
    case_description: str
    investigator: str
    case_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    items: list[ExifData] = None
    anomalies: list[Anomaly] = None
    audit_log: list[dict] = None
    map_html_path: Optional[str] = None
    map_image_path: Optional[str] = None


class ForensicReport:
    """Generate a multi-section forensic PDF report."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._register_styles()

    def _register_styles(self) -> None:
        self.styles.add(ParagraphStyle(
            name="ReportTitle", parent=self.styles["Title"],
            fontSize=22, leading=26, alignment=TA_CENTER,
            textColor=colors.HexColor("#102A43"), spaceAfter=12,
        ))
        self.styles.add(ParagraphStyle(
            name="SectionHeader", parent=self.styles["Heading1"],
            fontSize=14, leading=18,
            textColor=colors.HexColor("#102A43"),
            backColor=colors.HexColor("#E2ECFA"),
            borderPadding=4, spaceBefore=14, spaceAfter=8,
        ))
        self.styles.add(ParagraphStyle(
            name="SubHeader", parent=self.styles["Heading3"],
            fontSize=11, leading=14, spaceBefore=8, spaceAfter=4,
            textColor=colors.HexColor("#243B53"),
        ))
        self.styles.add(ParagraphStyle(
            name="Mono", parent=self.styles["BodyText"],
            fontName="Courier", fontSize=8, leading=10,
        ))
        self.styles.add(ParagraphStyle(
            name="Small", parent=self.styles["BodyText"],
            fontSize=8, leading=10, textColor=colors.HexColor("#444"),
        ))

    def generate(self, ctx: ReportContext, output_path: str | Path) -> Path:
        ctx.generated_at = ctx.generated_at or datetime.now()
        ctx.items = ctx.items or []
        ctx.anomalies = ctx.anomalies or []
        ctx.audit_log = ctx.audit_log or []
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(out), pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
            title=f"Forensic Report - {ctx.case_name}",
            author=ctx.investigator or APP_NAME,
        )
        story = []
        story.extend(self._cover(ctx))
        story.extend(self._summary(ctx))
        story.extend(self._anomalies_section(ctx))
        story.extend(self._evidence_section(ctx))
        if ctx.map_image_path and Path(ctx.map_image_path).exists():
            story.extend(self._map_section(ctx))
        story.extend(self._chain_of_custody(ctx))
        story.extend(self._signature(ctx))
        doc.build(story, onFirstPage=self._page_decoration,
                  onLaterPages=self._page_decoration)
        return out

    # ---------- sections ----------

    def _cover(self, ctx: ReportContext) -> list:
        s = self.styles
        meta_rows = [
            ["Case ID", str(ctx.case_id or "—")],
            ["Case Name", ctx.case_name],
            ["Investigator", ctx.investigator or "—"],
            ["Generated", ctx.generated_at.strftime("%Y-%m-%d %H:%M:%S")],
            ["Tool", f"{APP_NAME} v{APP_VERSION}"],
            ["Items", str(len(ctx.items))],
            ["Anomalies", str(len(ctx.anomalies))],
        ]
        t = Table(meta_rows, colWidths=[5 * cm, 11 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F4F8")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return [
            Spacer(1, 2 * cm),
            Paragraph("DIGITAL IMAGE FORENSIC REPORT", s["ReportTitle"]),
            Spacer(1, 0.3 * cm),
            Paragraph(
                f"<para alignment='center'><i>Case: {ctx.case_name}</i></para>",
                s["BodyText"]),
            Spacer(1, 1.2 * cm),
            t,
            Spacer(1, 0.6 * cm),
            Paragraph(ctx.case_description or "", s["BodyText"]),
            PageBreak(),
        ]


    def _summary(self, ctx: ReportContext) -> list:
        s = self.styles
        sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for a in ctx.anomalies:
            sv = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
            sev_counts[sv] = sev_counts.get(sv, 0) + 1
        with_gps = sum(1 for d in ctx.items if d.gps and d.gps.is_valid())
        with_exif = sum(1 for d in ctx.items if d.has_exif)
        cameras = {d.camera_model for d in ctx.items if d.camera_model}
        software = {d.software for d in ctx.items if d.software}
        rows = [
            ["Total evidence items", str(len(ctx.items))],
            ["Items with EXIF data", str(with_exif)],
            ["Items with valid GPS", str(with_gps)],
            ["Distinct camera models", str(len(cameras))],
            ["Distinct software signatures", str(len(software))],
            ["Critical anomalies", str(sev_counts["critical"])],
            ["High anomalies", str(sev_counts["high"])],
            ["Medium anomalies", str(sev_counts["medium"])],
            ["Low/info anomalies", str(sev_counts["low"] + sev_counts["info"])],
        ]
        t = Table(rows, colWidths=[8 * cm, 8 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1),
             [colors.white, colors.HexColor("#FAFBFC")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return [
            Paragraph("1. Executive Summary", s["SectionHeader"]),
            t, Spacer(1, 0.4 * cm),
        ]

    def _anomalies_section(self, ctx: ReportContext) -> list:
        s = self.styles
        out = [Paragraph("2. Anomaly Findings", s["SectionHeader"])]
        if not ctx.anomalies:
            out.append(Paragraph(
                "No anomalies were detected by the automated analysis.",
                s["BodyText"]))
            return out
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        sorted_a = sorted(
            ctx.anomalies,
            key=lambda a: order.get(
                a.severity.value if hasattr(a.severity, "value") else str(a.severity),
                9))
        rows = [["#", "Severity", "Code", "Title", "File"]]
        styles_extra = []
        for i, a in enumerate(sorted_a, start=1):
            sv = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
            file_name = Path(a.file_path).name if a.file_path else "-"
            rows.append([
                str(i), sv.upper(), a.code,
                Paragraph(a.title, s["Small"]),
                Paragraph(file_name, s["Small"]),
            ])
            color = SEVERITY_FILL.get(sv, colors.grey)
            styles_extra.append(("BACKGROUND", (1, i), (1, i), color))
            styles_extra.append(("TEXTCOLOR", (1, i), (1, i), colors.white))
        table = Table(rows, colWidths=[1 * cm, 2.2 * cm, 4 * cm, 5.3 * cm, 4 * cm],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102A43")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ] + styles_extra))
        out.append(table)
        out.append(Spacer(1, 0.4 * cm))
        for i, a in enumerate(sorted_a, start=1):
            sv = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
            details_text = ""
            if a.details:
                try:
                    details_text = json.dumps(a.details, indent=2, default=str)
                except (TypeError, ValueError):
                    details_text = str(a.details)
            block = [
                Paragraph(f"#{i} [{sv.upper()}] {a.title}", s["SubHeader"]),
                Paragraph(f"<b>Code:</b> {a.code}", s["BodyText"]),
                Paragraph(f"<b>File:</b> {a.file_path or '-'}", s["Small"]),
                Paragraph(a.description, s["BodyText"]),
            ]
            if details_text:
                block.append(Paragraph(
                    f"<font face='Courier' size='7'>"
                    f"{details_text.replace(chr(10), '<br/>')}</font>",
                    s["Small"]))
            out.append(KeepTogether(block))
            out.append(Spacer(1, 0.2 * cm))
        return out


    def _evidence_section(self, ctx: ReportContext) -> list:
        s = self.styles
        out = [Paragraph("3. Evidence Items", s["SectionHeader"])]
        if not ctx.items:
            out.append(Paragraph("No evidence items in this case.", s["BodyText"]))
            return out
        for idx, d in enumerate(ctx.items, start=1):
            block = self._evidence_block(idx, d)
            out.append(KeepTogether(block))
            out.append(Spacer(1, 0.3 * cm))
        return out

    def _evidence_block(self, idx: int, d: ExifData) -> list:
        s = self.styles
        gps_text = "—"
        if d.gps and d.gps.is_valid():
            gps_text = f"{d.gps.latitude:.6f}, {d.gps.longitude:.6f}"
            if d.gps.altitude is not None:
                gps_text += f" (alt {d.gps.altitude:.1f} m)"
        rows = [
            ["File name", d.file_name],
            ["File path", Paragraph(d.file_path, s["Small"])],
            ["Format / Mode", f"{d.image_format or '-'} / {d.image_mode or '-'}"],
            ["Dimensions", f"{d.image_width or '-'} x {d.image_height or '-'} px"],
            ["File size", f"{(d.file_size or 0):,} bytes"],
            ["Camera", " ".join(filter(None, [d.camera_make, d.camera_model])) or "-"],
            ["Lens", d.lens_model or "-"],
            ["Software", d.software or "-"],
            ["Date taken (Original)",
             d.datetime_original.isoformat() if d.datetime_original else "-"],
            ["Date digitized",
             d.datetime_digitized.isoformat() if d.datetime_digitized else "-"],
            ["File mtime",
             d.file_mtime.isoformat() if d.file_mtime else "-"],
            ["GPS", gps_text],
            ["Has EXIF", "Yes" if d.has_exif else "No"],
            ["EXIF tag count", str(len(d.raw_tags))],
        ]
        body = [
            Paragraph(f"3.{idx} {d.file_name}", s["SubHeader"]),
        ]
        if d.thumbnail_bytes:
            try:
                img = RLImage(io.BytesIO(d.thumbnail_bytes),
                              width=4 * cm, height=3 * cm, kind="proportional")
                body.append(img)
                body.append(Spacer(1, 0.15 * cm))
            except Exception:
                pass
        t = Table(rows, colWidths=[4.5 * cm, 11.5 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F4F8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        body.append(t)
        if d.extraction_errors:
            body.append(Paragraph(
                "<b>Extraction warnings:</b> " + "; ".join(d.extraction_errors),
                s["Small"]))
        return body

    def _map_section(self, ctx: ReportContext) -> list:
        s = self.styles
        out = [Paragraph("4. Geographic Distribution", s["SectionHeader"])]
        try:
            img = RLImage(str(ctx.map_image_path), width=16 * cm, height=10 * cm,
                          kind="proportional")
            out.append(img)
        except Exception as exc:
            out.append(Paragraph(f"Map unavailable: {exc}", s["Small"]))
        return out

    def _chain_of_custody(self, ctx: ReportContext) -> list:
        s = self.styles
        out = [Paragraph("5. Chain of Custody (Audit Log)", s["SectionHeader"])]
        if not ctx.audit_log:
            out.append(Paragraph("No audit entries recorded.", s["BodyText"]))
            return out
        rows = [["#", "Timestamp", "Actor", "Action", "Target"]]
        for i, entry in enumerate(ctx.audit_log, start=1):
            rows.append([
                str(i),
                entry.get("timestamp", "-"),
                entry.get("actor", "-"),
                entry.get("action", "-"),
                Paragraph(entry.get("target") or "-", s["Small"]),
            ])
        t = Table(rows, colWidths=[1 * cm, 4 * cm, 2.5 * cm, 4 * cm, 5 * cm],
                  repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102A43")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        out.append(t)
        return out

    def _signature(self, ctx: ReportContext) -> list:
        s = self.styles
        payload = json.dumps({
            "case_id": ctx.case_id,
            "case_name": ctx.case_name,
            "investigator": ctx.investigator,
            "generated_at": ctx.generated_at.isoformat(),
            "items": [d.file_path for d in ctx.items],
            "anomaly_codes": [a.code for a in ctx.anomalies],
        }, sort_keys=True, default=str)
        digest = hash_string(payload)
        return [
            Spacer(1, 0.6 * cm),
            Paragraph("6. Report Integrity", s["SectionHeader"]),
            Paragraph(
                "The SHA-256 digest below is computed over the canonical "
                "report payload (case identifier, investigator, generation "
                "timestamp, evidence file paths, and anomaly codes) and may "
                "be used to verify that this document was not altered after "
                "generation.", s["BodyText"]),
            Spacer(1, 0.2 * cm),
            Paragraph(f"<b>SHA-256:</b> <font face='Courier'>{digest}</font>",
                      s["BodyText"]),
        ]

    # ---------- page chrome ----------

    def _page_decoration(self, canvas, doc) -> None:
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(colors.HexColor("#102A43"))
        canvas.rect(0, h - 12 * mm, w, 12 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(2 * cm, h - 8 * mm, f"{APP_NAME} v{APP_VERSION}")
        canvas.drawRightString(w - 2 * cm, h - 8 * mm,
                               "CONFIDENTIAL - FORENSIC USE ONLY")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2 * cm, 1 * cm,
                          datetime.now().strftime("Generated %Y-%m-%d %H:%M:%S"))
        canvas.drawRightString(w - 2 * cm, 1 * cm, f"Page {doc.page}")
        canvas.restoreState()
