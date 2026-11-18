"""Convert numbers to Indian-currency words (lakh / crore system)."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Union

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
]


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _three_digits(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if rest:
        parts.append(_two_digits(rest))
    return " ".join(parts)


def number_to_indian_words(number: int) -> str:
    """1129 -> 'One Thousand One Hundred Twenty Nine'. Uses lakh/crore above 99,999."""
    if number == 0:
        return "Zero"
    if number < 0:
        return "Minus " + number_to_indian_words(-number)

    parts = []
    crore, number = divmod(number, 10_000_000)
    lakh, number = divmod(number, 100_000)
    thousand, number = divmod(number, 1_000)
    hundred = number

    if crore:
        parts.append(f"{number_to_indian_words(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if hundred:
        parts.append(_three_digits(hundred))
    return " ".join(p for p in parts if p)


def amount_to_words(amount: Union[int, float, Decimal, str]) -> str:
    """Format a rupee amount as words, e.g. 11129 -> 'Eleven Thousand ... Nine Only'."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative = value < 0
    value = abs(value)
    rupees = int(value)
    paise = int((value - rupees) * 100)

    words = number_to_indian_words(rupees)
    if paise:
        words += f" and {number_to_indian_words(paise)} Paise"
    words += " Only"
    return ("Minus " + words) if negative else words


def format_inr(amount: Union[int, float, Decimal, str], with_symbol: bool = True) -> str:
    """1234567.5 -> '12,34,567.50' using Indian digit grouping."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative = value < 0
    value = abs(value)
    whole, frac = f"{value:.2f}".split(".")

    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])

    out = f"{whole}.{frac}"
    if with_symbol:
        out = "Rs. " + out
    return ("-" + out) if negative else out
