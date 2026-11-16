"""The author's signature and the 'Buy me a coffee' (UPI) details. Edit this file to change them."""
from __future__ import annotations

from urllib.parse import quote

AUTHOR = "Sourav"
CREDIT = f"Developed by {AUTHOR}"

# Your UPI ID (for example "name@okbank") and the name shown in the payer's UPI app.
# While UPI_ID is empty, the coffee button and QR code are hidden and only the credit shows.
UPI_ID = "6296326307@ybl"
UPI_NAME = "Sourav Mahato"


def has_upi() -> bool:
    return bool(UPI_ID.strip())


def upi_uri(upi_id: str | None = None, name: str | None = None) -> str:
    """The standard UPI payment link. Any UPI app can scan it; the payer chooses the amount."""
    pa = (upi_id if upi_id is not None else UPI_ID).strip()
    pn = (name if name is not None else UPI_NAME).strip()
    return f"upi://pay?pa={quote(pa, safe='@.-_')}&pn={quote(pn)}&cu=INR"
