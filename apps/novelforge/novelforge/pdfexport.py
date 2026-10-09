"""
Styled PDF / EPUB-free export using ReportLab.

Cover page (optional art), decorative rules, a real table of contents, running
header, and "Page X of Y" footers via a two-pass NumberedCanvas.

Import is guarded: if reportlab isn't installed the rest of the app still works,
export just reports the pip command.
"""

import os

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, HRFlowable,
    )
    from reportlab.pdfgen import canvas
    REPORTLAB_OK = True
except Exception:
    REPORTLAB_OK = False


if REPORTLAB_OK:
    class _NumberedCanvas(canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                if self._pageNumber > 1:
                    self._decorate(total)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def _decorate(self, total):
            self.saveState()
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#8a8f98"))
            self.setStrokeColor(colors.HexColor("#d8dade"))
            self.setLineWidth(0.5)
            self.line(54, 800, 541, 800)
            self.drawString(54, 806, self._title.upper() if getattr(self, "_title", "") else "")
            self.drawRightString(541, 30, f"{self._pageNumber} / {total}")
            self.restoreState()


def export_pdf(project, out_path, cover_image=None, page_size=A4 if REPORTLAB_OK else None):
    if not REPORTLAB_OK:
        raise RuntimeError("PDF export needs reportlab. Run:  pip install reportlab")

    b = project.bible
    title = b.get("title") or project.name.replace("_", " ").title()

    doc = SimpleDocTemplate(out_path, pagesize=page_size,
                            leftMargin=58, rightMargin=58, topMargin=64, bottomMargin=54,
                            title=title, author="NovelForge")
    ss = getSampleStyleSheet()
    s_title = ParagraphStyle("t", parent=ss["Normal"], fontName="Helvetica-Bold",
                             fontSize=30, leading=36, alignment=TA_CENTER,
                             textColor=colors.HexColor("#16181d"))
    s_sub = ParagraphStyle("s", parent=ss["Normal"], fontName="Helvetica-Oblique",
                           fontSize=13, leading=18, alignment=TA_CENTER,
                           textColor=colors.HexColor("#5b616e"))
    s_h = ParagraphStyle("h", parent=ss["Normal"], fontName="Helvetica-Bold",
                         fontSize=17, leading=22, spaceBefore=8, spaceAfter=10,
                         textColor=colors.HexColor("#1f6feb"))
    s_body = ParagraphStyle("b", parent=ss["Normal"], fontName="Times-Roman",
                            fontSize=11.5, leading=17, alignment=TA_JUSTIFY, spaceAfter=7,
                            firstLineIndent=16)
    s_toc = ParagraphStyle("toc", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=11, leading=17)

    def esc(t):
        return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    story = [Spacer(1, 90), Paragraph(esc(title), s_title), Spacer(1, 14)]
    if b.get("series"):
        story.append(Paragraph(esc(f"{b['series'].replace('_', ' ').title()} — Book {b.get('book_index', 1)}"), s_sub))
    if b.get("genre"):
        story.append(Paragraph(esc(b["genre"]), s_sub))
    if cover_image and os.path.exists(cover_image):
        story.append(Spacer(1, 24))
        try:
            story.append(Image(cover_image, width=280, height=380))
        except Exception:
            pass
    story.append(PageBreak())

    n_chapters = project.chapter_count()
    story.append(Paragraph("Contents", s_h))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d8dade"), spaceAfter=14))
    for n in range(1, n_chapters + 1):
        ct = project.chapter_title(n)
        story.append(Paragraph(f"Chapter {n}" + (f" &nbsp;&nbsp; {esc(ct)}" if ct else ""), s_toc))
        story.append(Spacer(1, 3))
    story.append(PageBreak())

    for n in range(1, n_chapters + 1):
        ct = project.chapter_title(n)
        story.append(Paragraph(f"Chapter {n}" + (f" — {esc(ct)}" if ct else ""), s_h))
        story.append(HRFlowable(width="35%", thickness=1.2, color=colors.HexColor("#1f6feb"),
                                spaceAfter=12, hAlign="LEFT"))
        text = project.load_chapter(n)
        for para in text.split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(esc(para), s_body))
        story.append(PageBreak())

    def _on_page(cnv, _doc):
        cnv._title = title

    doc.build(story, canvasmaker=_NumberedCanvas, onFirstPage=_on_page, onLaterPages=_on_page)
    return out_path
