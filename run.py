"""Start ENES’AI SUPER MARKET.

    python run.py                 → development server on http://127.0.0.1:5000
    python run.py --prod          → Waitress production server (behind HTTPS reverse proxy)
    python run.py create-owner    → one-time owner account bootstrap
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
            pw = getpass("Fjalëkalimi (min. 12 shenja): ")
            pw2 = getpass("Përsërite fjalëkalimin: ")
            if pw != pw2:
                print("Fjalëkalimet nuk përputhen.")
                return 1
            ok, msg = create_owner(username, name, pw)
            print(msg)
            return 0 if ok else 1
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
