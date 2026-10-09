"""One totals rule everywhere (FUNCTIONAL_REQUIREMENTS §1.3):

    subtotal = Σ unit_price × qty          (unit price already includes the product discount)
    discount = round(subtotal × pct / 100)  (coupon; products only)
    delivery = 0 if (subtotal − discount) ≥ free_over (and free_over > 0) else fee; 0 for an empty cart
    total    = subtotal − discount + delivery
All amounts are whole lek; rounding is half-up like the design's Math.round."""
from ..util import round_half_up


def totals(lines, coupon_pct=0, fee=200, free_over=3000):
    """lines: iterable of (unit_price, qty)."""
    lines = list(lines)
    items = sum(int(q) for _, q in lines)
    sub = sum(int(p) * int(q) for p, q in lines)
    pct = int(coupon_pct or 0)
    disc = round_half_up(sub * pct, 100) if pct else 0
    after = sub - disc
    if not lines or (free_over > 0 and after >= free_over):
        delivery = 0
    else:
        delivery = int(fee)
    return {"items": items, "sub": sub, "pct": pct, "discount": disc, "after": after,
            "fee": delivery, "total": after + delivery}
