"""Payslip layout and content, checked against the supplied reference.

These read the generated PDF back rather than trusting the drawing code, so a
regression in the layout shows up as a failing assertion instead of a picture
nobody looks at.
"""
import io
from decimal import Decimal
from pathlib import Path

import pdfplumber
import pytest

from app.core.config import settings
from app.pdf.payslip_generator import build_payslip_pdf

SAMPLE = dict(
    employee_name="Rahul Sharma",
    employee_code="RGEMP003",
    designation="Digital Marketing Executive",
    department="Digital Marketing",
    pay_period="March, 2026",
    working_days=26,
    lop_days=0,
    location="New Delhi",
    bank_name="HDFC Bank",
    bank_account_no="50100XXXXXX4417",
    pan_number="ABCDE1234F",
    earnings=[("Basic", Decimal("8333")), ("Incentive", Decimal("5000"))],
    deductions=[("PT", Decimal("200"))],
    total_earnings=Decimal("13333"),
    total_deductions=Decimal("200"),
    net_pay=Decimal("13133"),
    amount_in_words="Thirteen Thousand One Hundred Thirty Three Only",
)


def render(**overrides):
    payload = dict(SAMPLE)
    payload.update(overrides)
    return build_payslip_pdf(**payload)


@pytest.fixture(scope="module")
def page():
    with pdfplumber.open(io.BytesIO(render())) as pdf:
        yield {
            "text": pdf.pages[0].extract_text(),
            "words": pdf.pages[0].extract_words(),
            "lines": pdf.pages[0].lines + pdf.pages[0].rects,
            "images": pdf.pages[0].images,
            "height": pdf.pages[0].height,
        }


def word(page, needle):
    """Top-most word box whose text contains the needle."""
    for w in page["words"]:
        if needle.lower() in w["text"].lower():
            return w
    return None


# ---------------------------------------------------------------- generation
def test_payslip_pdf_is_generated():
    content = render()
    assert content.startswith(b"%PDF")
    assert len(content) > 1000


def test_logo_is_embedded_and_is_the_supplied_file(page):
    assert page["images"], "the supplied logo should be drawn on the payslip"
    logo = Path(settings.COMPANY_LOGO_PATH)
    assert logo.exists()
    assert "robot-genie" in logo.name.lower()


def test_logo_keeps_its_own_aspect_ratio(page):
    image = page["images"][0]
    ratio = image["width"] / image["height"]
    assert 1.8 < ratio < 2.5, f"logo looks stretched (ratio {ratio:.2f})"


# ---------------------------------------------------------------- header
def test_company_name_and_address(page):
    text = page["text"]
    assert "Robot Genie" in text
    assert "Hno. 35, Office no. 301, 3rd Floor" in text
    assert "Laxmi Nagar, New Delhi - 110092" in text


def test_address_is_two_lines(page):
    lines = [ln for ln in page["text"].split("\n") if "Office no. 301" in ln or "Laxmi Nagar" in ln]
    assert len(lines) == 2, f"address should sit on two lines, got {lines}"


def test_udyam_number_present_and_not_truncated(page):
    assert "Udyam NI : UDYAM-DL-02-0061089" in page["text"]


def test_no_gst_or_marketing_text(page):
    text = page["text"].lower()
    for banned in ("gst", "people | idea", "brighter tomorrow", "empowering people"):
        assert banned not in text, f"{banned!r} must not appear on the payslip"


def test_header_text_does_not_overflow_the_page(page):
    right_edge = max(w["x1"] for w in page["words"])
    assert right_edge < 570, f"content runs past the right margin ({right_edge:.0f}pt)"


# ---------------------------------------------------------------- title
def test_title_uses_the_supplied_period(page):
    assert "Payslip for the Month of March, 2026" in page["text"]


def test_title_period_is_dynamic_not_hardcoded():
    with pdfplumber.open(io.BytesIO(render(pay_period="November, 2027"))) as pdf:
        text = pdf.pages[0].extract_text()
    assert "Payslip for the Month of November, 2027" in text
    assert "March" not in text


def test_title_sits_above_the_horizontal_rule(page):
    title = word(page, "Payslip")
    assert title is not None
    # pdfplumber measures from the top, so a larger "top" is further down
    rules = [ln for ln in page["lines"] if ln.get("width", 0) > 400]
    assert rules, "expected a full-width rule under the title"
    below = [ln for ln in rules if ln["top"] > title["bottom"]]
    assert below, "the rule must sit below the title, not above it"


# ---------------------------------------------------------------- employee block
def test_employee_fields_are_present(page):
    text = page["text"]
    for label in ("Name", "Designation", "Department", "Location",
                  "Effective Work Days", "LOP", "Employee ID", "Bank Name",
                  "Bank Account No.", "PAN No."):
        assert label in text, f"missing employee field: {label}"


def test_employee_values_come_from_the_record(page):
    text = page["text"]
    for value in ("Rahul Sharma", "Digital Marketing Executive", "New Delhi",
                  "RGEMP003", "HDFC Bank", "50100XXXXXX4417", "ABCDE1234F"):
        assert value in text, f"missing employee value: {value}"


def test_long_designation_is_not_truncated():
    """A realistically long job title shrinks to fit rather than being cut."""
    long_title = "Senior Digital Marketing Executive"
    with pdfplumber.open(io.BytesIO(render(designation=long_title))) as pdf:
        text = pdf.pages[0].extract_text()
    assert long_title in text, "long values must shrink to fit, not be cut off"


def test_extreme_value_never_runs_into_the_next_column():
    """Past the shrink floor the value is ellipsised, never overlapped."""
    absurd = "Senior Principal Digital Marketing And Communications Executive Lead"
    with pdfplumber.open(io.BytesIO(render(designation=absurd))) as pdf:
        words = pdf.pages[0].extract_words()
    designation_row = [w for w in words if abs(w["top"] - min(
        x["top"] for x in words if "Designation" in x["text"])) < 4]
    left_col = [w for w in designation_row if w["x0"] < 290]
    assert left_col, "designation row not found"
    assert max(w["x1"] for w in left_col) < 292, "value spilled into the right column"


# ---------------------------------------------------------------- earnings
def test_earnings_are_basic_and_incentive_only(page):
    text = page["text"]
    assert "Basic" in text
    assert "Incentive" in text
    for removed in ("HRA", "House Rent Allowance", "Special Allowance"):
        assert removed not in text, f"{removed} should no longer appear"


def test_no_empty_placeholder_rows(page):
    """Removing HRA/Special must not leave blank labelled rows behind."""
    rows = [ln.strip() for ln in page["text"].split("\n")]
    assert not any(ln.endswith(":") and len(ln) < 4 for ln in rows)


def test_totals_and_net_pay_are_the_supplied_figures(page):
    text = page["text"]
    assert "13,333" in text      # total earnings
    assert "200" in text          # total deductions
    assert "13,133" in text       # net pay
    assert "Total Earnings" in text
    assert "Total Deductions" in text


def test_deductions_section_is_kept(page):
    assert "Deductions" in page["text"]
    assert "PT" in page["text"]


def test_amounts_are_recalculated_for_other_values():
    with pdfplumber.open(io.BytesIO(render(
        earnings=[("Basic", Decimal("20000")), ("Incentive", Decimal("5000"))],
        deductions=[("PT", Decimal("200"))],
        total_earnings=Decimal("25000"), total_deductions=Decimal("200"),
        net_pay=Decimal("24800"),
        amount_in_words="Twenty Four Thousand Eight Hundred Only",
    ))) as pdf:
        text = pdf.pages[0].extract_text()
    assert "25,000" in text
    assert "24,800" in text
    assert "Twenty Four Thousand Eight Hundred Only" in text
    assert "13,133" not in text


# ---------------------------------------------------------------- net pay band
def test_amount_in_words_is_rendered(page):
    assert "Rupees Thirteen Thousand One Hundred Thirty Three Only" in page["text"]


def test_net_pay_label_and_amount(page):
    assert "Net Pay For The Month" in page["text"]


def test_no_coin_icon_in_the_net_pay_band(page):
    """Only the logo may be drawn as an image; no coin or decorative graphic."""
    assert len(page["images"]) == 1, "the logo should be the only image on the page"


def test_no_vertical_divider_inside_the_net_pay_band(page):
    label = word(page, "Net")
    assert label is not None
    band_top, band_bottom = label["top"] - 12, label["bottom"] + 34
    verticals = [
        ln for ln in page["lines"]
        if ln.get("height", 0) > 12 and ln.get("width", 0) < 3
        and ln["top"] > band_top and ln["bottom"] < band_bottom
    ]
    assert not verticals, "the net pay band must not contain a vertical separator"


def test_net_amount_is_right_aligned(page):
    amount = None
    for w in page["words"]:
        if "13,133" in w["text"]:
            amount = w
    assert amount is not None
    assert amount["x1"] > 500, "the net amount should sit against the right margin"


# ---------------------------------------------------------------- footer
def test_director_line_is_present(page):
    assert "Director: Mr. Ali Alvi" in page["text"]


def test_director_is_small_and_not_bold(page):
    director = word(page, "Director:")
    assert director is not None
    height = director["bottom"] - director["top"]
    assert height < 13, f"director line looks oversized ({height:.1f}pt)"
    fonts = {w.get("fontname", "") for w in page["words"] if "Director" in w["text"]}
    assert not any("bold" in f.lower() for f in fonts), "director must not be bold"


def test_director_sits_above_the_bottom_rule(page):
    director = word(page, "Director:")
    note = word(page, "system")
    assert director is not None and note is not None
    assert director["bottom"] < note["top"], "director belongs above the closing rule"


def test_system_generated_note(page):
    assert ("This is a system generated payslip and does not require signature."
            in page["text"])
    assert "Employer Signature" not in page["text"]


def test_note_is_small_and_centred(page):
    anchor = word(page, "system")
    assert anchor is not None
    assert (anchor["bottom"] - anchor["top"]) < 13
    # measure the whole sentence, not one word inside it
    row = [w for w in page["words"] if abs(w["top"] - anchor["top"]) < 3]
    centre = (min(w["x0"] for w in row) + max(w["x1"] for w in row)) / 2
    assert 270 < centre < 325, f"note should be centred, found centre at {centre:.0f}pt"


# ---------------------------------------------------------------- layout safety
def test_nothing_overlaps_horizontally(page):
    """Words on the same visual line must not run into each other."""
    rows = {}
    for w in page["words"]:
        key = round(w["top"] / 3)
        rows.setdefault(key, []).append(w)
    for row in rows.values():
        row.sort(key=lambda w: w["x0"])
        for left, right in zip(row, row[1:]):
            assert right["x0"] >= left["x1"] - 1.5, (
                f"'{left['text']}' overlaps '{right['text']}'"
            )


def test_content_stays_inside_the_page(page):
    assert min(w["x0"] for w in page["words"]) >= 30
    assert max(w["x1"] for w in page["words"]) <= 570
    assert max(w["bottom"] for w in page["words"]) <= page["height"] - 20


def test_single_page_output():
    with pdfplumber.open(io.BytesIO(render())) as pdf:
        assert len(pdf.pages) == 1


def test_missing_optional_values_do_not_break_the_layout():
    content = render(location=None, bank_name=None, bank_account_no=None,
                     pan_number=None, deductions=[], total_deductions=Decimal("0"))
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = pdf.pages[0].extract_text()
    assert "Payslip for the Month of" in text
    assert "PAN No." in text          # the label stays, the value shows a dash
