"""Demo orders for development (fictitious people, is_demo=1) — same set as the prototype."""
import secrets

from ..util import phone_digits
from . import orders

ZONES = {"Lungomare": (40.45338, 19.48262), "Skelë": (40.46021, 19.48047), "Qendër": (40.46684, 19.48931), "Uji i Ftohtë": (40.42951, 19.49003)}
DEMO = [
    ("2026-10-08T11:02:37", "Ervin Shehu", "069 330 7781", "", "Skelë", "Rr. Dervish Hekali, Pall. 5", "", [(5031, 1), (5020, 2), (3011, 1)], None, "cancel"),
    ("2026-10-08T11:55:10", "Klodiana Rama", "068 912 0045", "k.rama@gmail.com", "Lungomare", "Rr. Lungomare, Pall. 9, Ap. 4", "", [(1050, 1), (1042, 1), (3002, 1)], None, "done"),
    ("2026-10-08T12:40:44", "Gentian Muça", "069 801 3311", "", "Uji i Ftohtë", "Rr. Uji i Ftohtë, Vila 7", "Porta e bardhë", [(2107, 2), (1043, 2), (4005, 2), (3002, 3)], None, "route"),
    ("2026-10-08T13:12:05", "Mirela Daci", "067 220 9384", "m.daci@outlook.com", "Qendër", "Sheshi i Flamurit, Pall. 2, Kati 3", "Telefononi kur të arrini", [(5031, 2), (3011, 2), (5020, 3), (2107, 1)], None, "prep"),
    ("2026-10-08T13:48:30", "Arben Kola", "068 455 1290", "arben.kola@yahoo.com", "Skelë", "Rr. Kosova, Pall. 4, Ap. 11", "", [(1042, 2), (3002, 2), (4005, 3)], None, "new"),
    ("2026-10-08T14:05:12", "Elira Hoxha", "069 123 4567", "elira.h@gmail.com", "Lungomare", "Rr. Ismail Qemali, Pall. 12, Sh. 2, Ap. 8", "Zileja e dytë", [(1050, 2), (1043, 3), (3011, 1), (3002, 2), (5031, 1)], "VLORE10", "new"),
]


def seed_orders(con):
    if con.execute("SELECT 1 FROM orders WHERE is_demo=1").fetchone():
        return
    for at, who, phone, email, zone, addr, note, items, coupon, status in DEMO:
        name, surname = who.split(" ", 1)
        lat, lng = ZONES[zone]
        v = {"name": name, "surname": surname, "phone": phone, "email": email, "optin": bool(email), "city": "Vlorë", "zone": zone,
             "address": addr, "note": note, "terms": True, "pay": "cash"}
        o, _t = orders.create_order(v, {"lat": lat, "lng": lng, "src": "gps", "acc": 12}, items, coupon, secrets.token_urlsafe(24),
                                    con=con, is_demo=True, created_at=at)
        con.execute("UPDATE orders SET wa_opened_at = CASE WHEN ? <> 'cancel' THEN created_at END WHERE id=?", (status, o["id"]))
        if status != "new":
            if status == "cancel":
                orders.change_status(o["nr"], "cancel", None, con)
            else:
                con.execute("UPDATE orders SET status=?, status_changed_at=created_at WHERE id=?", (status, o["id"]))
    emails = [d[3] for d in DEMO if d[3]]
    con.execute("UPDATE subscribers SET is_demo=1 WHERE email IN (%s)" % ",".join("?" * len(emails)), emails)
    print("U shtuan 6 porosi demo.")
