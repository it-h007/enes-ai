"""Error pages: public 404 uses the designed page (HTTP 404); others are generic and leak nothing."""
from flask import current_app, jsonify, render_template, request


def _wants_json():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json" \
        or request.headers.get("X-Requested-With") == "fetch"


def register(app):
    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify(error="not_found"), 404
        return render_template("pages/404.html", active=None, noindex=True), 404

    @app.errorhandler(403)
    def forbidden(e):
        if _wants_json():
            return jsonify(error="forbidden"), 403
        return render_template("errors/error.html", code=403, title="Nuk keni leje",
                               text="Ky veprim kërkon një leje që llogaria juaj nuk e ka. Kërkojini pronarit."), 403

    @app.errorhandler(400)
    def bad_request(e):
        csrf = getattr(e, "description", "") == "csrf"
        if _wants_json():
            return jsonify(error="csrf" if csrf else "bad_request"), 400
        return render_template("errors/error.html", code=400, title="Kërkesa nuk u pranua",
                               text=("Sesioni skadoi ose formulari është i vjetër. Rifreskoni faqen dhe provoni sërish." if csrf
                                     else "Kërkesa nuk është e vlefshme.")), 400

    @app.errorhandler(429)
    def too_many(e):
        if _wants_json():
            return jsonify(error="rate_limited"), 429
        return render_template("errors/error.html", code=429, title="Shumë përpjekje",
                               text="Prisni pak minuta dhe provoni sërish."), 429

    @app.errorhandler(413)
    def too_large(e):
        if _wants_json():
            return jsonify(error="too_large"), 413
        return render_template("errors/error.html", code=413, title="Skedari është shumë i madh",
                               text="Madhësia maksimale është 20 MB."), 413

    @app.errorhandler(500)
    def server_error(e):
        current_app.logger.exception("Server error on %s", request.path)
        if _wants_json():
            return jsonify(error="server"), 500
        return render_template("errors/error.html", code=500, title="Diçka shkoi keq",
                               text="Gabimi u regjistrua. Provoni sërish pas pak."), 500
