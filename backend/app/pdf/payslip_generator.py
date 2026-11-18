"""Payslip PDF generation.

The layout follows the supplied payslip reference exactly:

    logo | company name, address, Udyam NI
    centred "Payslip for the Month of <Month>, <Year>"
    horizontal rule beneath the title
    two-column employee information box
    Earnings / Deductions tables side by side with light blue headers
    Net Pay band: label and amount in words on the left, amount on the right
    "Director: Mr. Ali Alvi" above the closing rule
    centred system-generated note

Nothing on the page is hard-coded: every value is passed in from the salary and
employee records. The month in the title comes from the salary period, so
"March, 2026" is only what the sample data happens to produce.
"""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas

from app.core.config import settings

PAGE_W, PAGE_H = A4
MARGIN = 40.0

# Palette taken from the reference: navy rules, very light blue table headers.
INK = colors.HexColor("#1A1A1A")
NAVY = colors.HexColor("#1F3864")
RULE = colors.HexColor("#2F5597")
GRID = colors.HexColor("#8EA9C1")
HEAD_BG = colors.HexColor("#EDF1F8")
BAND_BG = colors.HexColor("#F4F7FC")
LINK = colors.HexColor("#2F5597")
WHITE = colors.white

# The reference sets the rupee sign, which the built-in Helvetica cannot draw.
RUPEE = "\u20B9"
FONT_R = "Helvetica"
FONT_B = "Helvetica-Bold"
_RUPEE_FONT = None


def _register_unicode_font() -> None:
    """Find a TrueType face that can render the rupee sign, if one is installed."""
    global _RUPEE_FONT, FONT_R, FONT_B
    if _RUPEE_FONT is not None:
        return
    candidates = [
        ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("LiberationSans", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "LiberationSans-Bold", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for name, path, bold_name, bold_path in candidates:
        if Path(path).exists() and Path(bold_path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                FONT_R, FONT_B = name, bold_name
                _RUPEE_FONT = name
                return
            except Exception:  # noqa: BLE001 - fall back to Helvetica
                break
    _RUPEE_FONT = ""


def _money(value) -> str:
    """Indian grouping without a currency symbol: 13333 -> 13,333."""
    if value is None:
        value = 0
    amount = Decimal(str(value)).quantize(Decimal("1"))
    negative = amount < 0
    digits = str(abs(amount))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join(parts + [tail])
    return ("-" if negative else "") + digits


def _rupee(value) -> str:
    return (RUPEE if _RUPEE_FONT else "Rs. ") + _money(value)


class PayslipCanvas:
    def __init__(self, buffer: BytesIO):
        self.c = pdf_canvas.Canvas(buffer, pagesize=A4)

    def text(self, x, y, value, size=8.5, bold=False, colour=INK, font=None):
        self.c.setFillColor(colour)
        self.c.setFont(font or (FONT_B if bold else FONT_R), size)
        self.c.drawString(x, y, str(value))

    def text_center(self, cx, y, value, size=8.5, bold=False, colour=INK):
        self.c.setFillColor(colour)
        self.c.setFont(FONT_B if bold else FONT_R, size)
        self.c.drawCentredString(cx, y, str(value))

    def text_right(self, x, y, value, size=8.5, bold=False, colour=INK):
        self.c.setFillColor(colour)
        self.c.setFont(FONT_B if bold else FONT_R, size)
        self.c.drawRightString(x, y, str(value))

    def hline(self, y, width=0.8, colour=RULE, x1=None, x2=None):
        self.c.setStrokeColor(colour)
        self.c.setLineWidth(width)
        self.c.line(x1 if x1 is not None else MARGIN, y,
                    x2 if x2 is not None else PAGE_W - MARGIN, y)

    def vline(self, x, y1, y2, width=0.8, colour=GRID):
        self.c.setStrokeColor(colour)
        self.c.setLineWidth(width)
        self.c.line(x, y1, x, y2)

    def box(self, x, y, w, h, stroke=GRID, fill=None, width=0.8):
        self.c.setStrokeColor(stroke)
        self.c.setLineWidth(width)
        if fill is not None:
            self.c.setFillColor(fill)
        self.c.rect(x, y, w, h, stroke=1, fill=1 if fill is not None else 0)


def _logo_path() -> Optional[Path]:
    configured = settings.COMPANY_LOGO_PATH
    if configured and Path(configured).exists():
        return Path(configured)
    return None


def _draw_logo(pc: PayslipCanvas, x: float, cy: float, max_w: float, max_h: float) -> bool:
    """Draw the supplied logo at its own aspect ratio, vertically centred."""
    path = _logo_path()
    if path is None:
        return False
    try:
        image = ImageReader(str(path))
        iw, ih = image.getSize()
    except Exception:  # noqa: BLE001 - a missing logo must not break payroll
        return False
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    pc.c.drawImage(image, x, cy - h / 2, width=w, height=h,
                   mask="auto", preserveAspectRatio=True, anchor="c")
    return True


def _fit(canvas_obj, text: str, font: str, size: float, max_width: float,
         floor: float = 6.2) -> float:
    """Largest size at or below `size` at which `text` fits `max_width`."""
    while size > floor and canvas_obj.stringWidth(str(text), font, size) > max_width:
        size -= 0.2
    return size


def _wrap(text: str, font: str, size: float, max_width: float, canvas_obj) -> List[str]:
    words, lines, current = str(text or "").split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if canvas_obj.stringWidth(trial, font, size) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _address_lines(address: str, canvas_obj, size: float, max_width: float) -> List[str]:
    """Two balanced lines, splitting on a comma near the middle where possible."""
    text = " ".join(str(address or "").split())
    if canvas_obj.stringWidth(text, FONT_R, size) <= max_width:
        return [text]
    parts = [p.strip() for p in text.split(",")]
    best, best_gap = None, None
    for i in range(1, len(parts)):
        first = ", ".join(parts[:i])
        second = ", ".join(parts[i:])
        w1 = canvas_obj.stringWidth(first + ",", FONT_R, size)
        w2 = canvas_obj.stringWidth(second, FONT_R, size)
        if w1 > max_width or w2 > max_width:
            continue
        gap = abs(w1 - w2)
        if best_gap is None or gap < best_gap:
            best, best_gap = [first + ",", second], gap
    return best or _wrap(text, FONT_R, size, max_width, canvas_obj)[:2]


def build_payslip_pdf(
    *,
    employee_name: str,
    employee_code: str,
    designation: str,
    department: str,
    pay_period: str,
    working_days,
    earnings: Sequence[Tuple[str, Decimal]],
    deductions: Sequence[Tuple[str, Decimal]],
    total_earnings: Decimal,
    total_deductions: Decimal,
    net_pay: Decimal,
    amount_in_words: str,
    location: Optional[str] = None,
    lop_days=0,
    bank_name: Optional[str] = None,
    bank_account_no: Optional[str] = None,
    pan_number: Optional[str] = None,
    company_name: Optional[str] = None,
    company_address: Optional[str] = None,
    company_udyam: Optional[str] = None,
    director_name: Optional[str] = None,
) -> bytes:
    """Render one payslip and return the PDF bytes."""
    _register_unicode_font()

    company_name = company_name or settings.COMPANY_NAME
    company_address = company_address or settings.COMPANY_ADDRESS
    company_udyam = company_udyam or getattr(settings, "COMPANY_UDYAM", "")
    director_name = director_name or getattr(settings, "COMPANY_DIRECTOR", "Mr. Ali Alvi")

    buffer = BytesIO()
    pc = PayslipCanvas(buffer)
    c = pc.c
    c.setTitle(f"Payslip - {employee_name} - {pay_period}")
    c.setAuthor(company_name)
    c.setSubject(f"Salary slip for {pay_period}")

    left, right = MARGIN, PAGE_W - MARGIN
    width = right - left

    # ------------------------------------------------ header: logo | company
    header_top = PAGE_H - MARGIN
    header_h = 88.0
    header_cy = header_top - header_h / 2

    # Divider sits left of centre so the address has room, as the reference does.
    divider_x = left + 172
    logo_drawn = _draw_logo(pc, left + 6, header_cy, divider_x - left - 20, header_h - 10)
    if not logo_drawn:
        pc.text(left + 6, header_cy - 4, company_name, size=13, bold=True, colour=NAVY)
    pc.vline(divider_x, header_top - header_h + 4, header_top - 2, width=0.9, colour=GRID)

    info_x = divider_x + 18
    info_w = right - info_x
    y = header_top - 17
    pc.text(info_x, y, company_name, size=17, bold=True, colour=INK)

    # Address: smaller than the company name, two balanced lines, never overflowing.
    y -= 19
    for line in _address_lines(company_address, c, 9.0, info_w):
        pc.text(info_x, y, line, size=9.0, colour=INK)
        y -= 12.5

    if company_udyam:
        y -= 3
        pc.text(info_x, y, f"Udyam NI : {company_udyam}", size=9.0, colour=INK)

    # ------------------------------------------------ title, then the rule
    title_y = header_top - header_h - 34
    pc.text_center(PAGE_W / 2, title_y,
                   f"Payslip for the Month of {pay_period}", size=17.5, bold=True, colour=INK)
    rule_y = title_y - 18
    pc.hline(rule_y, width=1.0, colour=RULE)

    # ------------------------------------------------ employee information box
    box_top = rule_y - 22
    rows_left = [
        ("Name", employee_name),
        ("Designation", designation),
        ("Department", department),
        ("Location", location or "-"),
        ("Effective Work Days", str(working_days if working_days is not None else "-")),
        ("LOP", str(lop_days if lop_days is not None else 0)),
    ]
    rows_right = [
        ("Employee ID", employee_code),
        ("Bank Name", bank_name or "-"),
        ("Bank Account No.", bank_account_no or "-"),
        ("PAN No.", pan_number or "-"),
    ]

    row_h = 27.0
    box_h = row_h * len(rows_left) + 16
    box_bottom = box_top - box_h
    pc.box(left, box_bottom, width, box_h)
    mid_x = left + width / 2
    pc.vline(mid_x, box_bottom, box_top)

    def draw_info(rows, x0, col_w):
        label_x = x0 + 12
        colon_x = x0 + col_w * 0.47
        value_x = colon_x + 10
        value_right = x0 + col_w - 14
        yy = box_top - 26
        for label, value in rows:
            label_size = _fit(c, label, FONT_R, 9.4, colon_x - label_x - 6)
            pc.text(label_x, yy, label, size=label_size, colour=INK)
            pc.text(colon_x, yy, ":", size=9.4, colour=INK)
            # value sits on a thin rule, exactly as the reference shows.
            # Long values shrink to fit rather than being cut off.
            text = str(value or "-")
            avail = value_right - value_x
            size = _fit(c, text, FONT_R, 9.4, avail, floor=5.8)
            # Only an extreme value can still be too wide at the floor size; clip
            # it with an ellipsis so it can never run into the next column.
            if c.stringWidth(text, FONT_R, size) > avail:
                while len(text) > 4 and c.stringWidth(text + "\u2026", FONT_R, size) > avail:
                    text = text[:-1]
                text += "\u2026"
            pc.text(value_x, yy, text, size=size, colour=INK)
            pc.hline(yy - 3, width=0.6, colour=GRID, x1=value_x, x2=value_right)
            yy -= row_h

    draw_info(rows_left, left, width / 2)
    draw_info(rows_right, mid_x, width / 2)

    # ------------------------------------------------ earnings / deductions
    table_top = box_bottom - 22
    col_w = width / 2
    amt_w = 132.0
    head_h = 30.0

    earn_rows = list(earnings)
    ded_rows = list(deductions)
    body_rows = max(len(earn_rows), len(ded_rows), 1)
    body_h = row_h * body_rows
    total_h = 30.0
    table_h = head_h + body_h + total_h
    table_bottom = table_top - table_h

    # header band
    pc.box(left, table_top - head_h, width, head_h, fill=HEAD_BG)
    head_size = 10.2
    pc.text(left + 14, table_top - head_h + 11, "Earnings", size=head_size, bold=True)
    pc.text_right(left + col_w - 14, table_top - head_h + 11,
                  f"Amount ({RUPEE if _RUPEE_FONT else 'Rs'})", size=10.2, bold=True)
    pc.text(mid_x + 14, table_top - head_h + 11, "Deductions", size=10.2, bold=True)
    pc.text_right(right - 14, table_top - head_h + 11,
                  f"Amount ({RUPEE if _RUPEE_FONT else 'Rs'})", size=10.2, bold=True)

    # body rows
    yy = table_top - head_h - 18
    for i in range(body_rows):
        if i < len(earn_rows):
            name, amount = earn_rows[i]
            pc.text(left + 14, yy, name, size=9.6)
            pc.text_right(left + col_w - 14, yy, _money(amount), size=9.6)
        if i < len(ded_rows):
            name, amount = ded_rows[i]
            pc.text(mid_x + 14, yy, name, size=9.6)
            pc.text_right(right - 14, yy, _money(amount), size=9.6)
        yy -= row_h

    # totals band
    totals_top = table_bottom + total_h
    pc.box(left, table_bottom, width, total_h, fill=HEAD_BG)
    label_w = col_w - amt_w - 20
    te_label, td_label = "Total Earnings (Rs)", "Total Deductions (Rs)"
    total_size = min(_fit(c, te_label, FONT_B, 10, label_w),
                     _fit(c, td_label, FONT_B, 10, label_w))
    pc.text(left + 14, table_bottom + 11, te_label, size=total_size, bold=True)
    pc.text_right(left + col_w - 14, table_bottom + 11, _money(total_earnings), size=10, bold=True)
    pc.text(mid_x + 14, table_bottom + 11, td_label, size=total_size, bold=True)
    pc.text_right(right - 14, table_bottom + 11, _money(total_deductions), size=10, bold=True)

    # outer frame and column rules
    pc.box(left, table_bottom, width, table_h)
    pc.vline(mid_x, table_bottom, table_top)
    pc.vline(left + col_w - amt_w, table_bottom, table_top)
    pc.vline(right - amt_w, table_bottom, table_top)
    pc.hline(table_top - head_h, width=0.8, colour=GRID)
    pc.hline(totals_top, width=0.8, colour=GRID)

    # ------------------------------------------------ net pay band
    band_top = table_bottom - 26
    band_h = 58.0
    band_bottom = band_top - band_h
    pc.box(left, band_bottom, width, band_h, fill=BAND_BG)

    # No coin icon and no vertical divider inside this band, by design.
    pc.text(left + 16, band_top - 24, "Net Pay For The Month:", size=14, bold=True, colour=INK)
    words = f"(Rupees {amount_in_words.strip()})" if amount_in_words else ""
    words_max = width - 190
    words_size = 9.4
    while c.stringWidth(words, FONT_R, words_size) > words_max and words_size > 6.2:
        words_size -= 0.2
    pc.text(left + 16, band_top - 41, words, size=words_size, colour=INK)
    pc.text_right(right - 16, band_top - 38, _rupee(net_pay), size=21, bold=True, colour=INK)

    # ------------------------------------------------ director + closing rule
    director_y = band_bottom - 30
    pc.text_right(right, director_y, f"Director: {director_name}", size=9.4, bold=False)

    close_y = director_y - 16
    pc.hline(close_y, width=0.9, colour=RULE)
    pc.text_center(PAGE_W / 2, close_y - 16,
                   "This is a system generated payslip and does not require signature.",
                   size=9.4, colour=LINK)

    c.showPage()
    c.save()
    return buffer.getvalue()
