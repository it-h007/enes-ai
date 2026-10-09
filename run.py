"""Start ENES’AI SUPER MARKET.

    python run.py                 → development server on http://127.0.0.1:5000
    python run.py --prod          → Waitress production server (behind HTTPS reverse proxy)
    python run.py create-owner    → one-time owner account bootstrap
    python run.py reset-password  → new password for a user (local console only), clears lockout
"""
import os
import sys

from enesai import create_app


def main(argv):
    if argv and argv[0] == "create-owner":
        from getpass import getpass
        app = create_app()
        with app.app_context():
            from enesai.services.auth import create_owner
            username = input("Emri i përdoruesit (pronari): ").strip()
            name = input("Emri i plotë [Pronari]: ").strip() or "Pronari"
            pw = getpass("Fjalëkalimi (min. 12 shenja; nuk shfaqet kur shkruani): ")
            pw2 = getpass("Përsërite fjalëkalimin: ")
            if pw != pw2:
                print("Fjalëkalimet nuk përputhen.")
                return 1
            ok, msg = create_owner(username, name, pw)
            print(msg)
            return 0 if ok else 1
    if argv and argv[0] == "reset-password":
        from getpass import getpass
        app = create_app()
        with app.app_context():
            from enesai.db import get_db
            from enesai.services.auth import reset_password
            rows = get_db().execute("SELECT username, role FROM operators ORDER BY role='owner' DESC, username").fetchall()
            if not rows:
                print("Nuk ka asnjë llogari. Krijoni pronarin me: python run.py create-owner")
                return 1
            print("Llogaritë: " + ", ".join("%s (%s)" % (r["username"], "pronar" if r["role"] == "owner" else r["role"]) for r in rows))
            default = rows[0]["username"]
            username = input("Emri i përdoruesit [%s]: " % default).strip() or default
            pw = getpass("Fjalëkalimi i ri (pronari min. 12 shenja; nuk shfaqet kur shkruani): ")
            if pw != getpass("Përsërite fjalëkalimin: "):
                print("Fjalëkalimet nuk përputhen.")
                return 1
            err = reset_password(username, pw)
            print(err or "Fjalëkalimi u ndryshua për @%s. Bllokimi u hoq. Hyni te /paneli." % username.strip().lower())
            return 1 if err else 0
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app = create_app()
    if "--prod" in argv or app.config["ENV"] == "production":
        from waitress import serve
        print("ENES’AI: Waitress në http://%s:%d (vendoseni pas HTTPS)" % (host, port))
        serve(app, host=host, port=port, threads=8)
    else:
        print("ENES’AI (zhvillim): http://%s:%d   Paneli: http://%s:%d%s" % (host, port, host, port, app.config["ADMIN_PATH"]))
        app.run(host=host, port=port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
