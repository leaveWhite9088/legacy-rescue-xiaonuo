# -*- coding: utf-8 -*-
"""Flask 应用入口、跨代中间件挂载、钩子注册与多蓝图装配中心。"""
import os
import traceback
from flask import Flask, jsonify, send_from_directory

from app.hooks import register_all_hooks
from app.infra.cache import clear_all_runtime_caches
from app.infra.config import BASE_DIR, DB_PATH, EXPORT_DIR, FEATURE_FLAGS
from app.middleware import register_middlewares
from app.routes.admin import bp as admin_bp
from app.routes.analytics import bp as analytics_bp
from app.routes.approvals import bp as approvals_bp
from app.routes.billing import bp as billing_bp
from app.routes.diagnostics import bp as diagnostics_bp
from app.routes.fapiao import bp as fapiao_bp
from app.routes.partners import bp as partners_bp
from app.routes.subscriptions import bp as subscriptions_bp
from app.routes.usage import bp as usage_bp
from app.routes.wallet import bp as wallet_bp


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["DB_PATH"] = db_path or DB_PATH
    app.config["EXPORT_DIR"] = EXPORT_DIR
    os.environ["YUNCE_DB_PATH"] = app.config["DB_PATH"]

    clear_all_runtime_caches()
    register_all_hooks()
    register_middlewares(app)

    app.register_blueprint(subscriptions_bp)
    app.register_blueprint(usage_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(partners_bp)
    app.register_blueprint(fapiao_bp)
    app.register_blueprint(approvals_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(diagnostics_bp)
    app.register_blueprint(admin_bp)

    static_dir = str(BASE_DIR / "static")

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service": "yunce-billing-center",
            "version": "2.6.0-ent",
            "v3_pipeline_enabled": bool(FEATURE_FLAGS.get("ENABLE_V3_BILLING_PIPELINE", False)),
        })

    @app.route("/")
    def index():
        return send_from_directory(static_dir, "portal.html")

    @app.route("/admin")
    def admin_page():
        return send_from_directory(static_dir, "admin.html")

    @app.route("/legacy-portal")
    def legacy_portal_page():
        return send_from_directory(static_dir, "legacy_index_2024.html")

    @app.route("/static/<path:filename>")
    def serve_static(filename: str):
        return send_from_directory(static_dir, filename)

    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        body = {"error": "Internal Server Error"}
        if FEATURE_FLAGS.get("VERBOSE_500_DIAGNOSTICS", True):
            body["error"] = str(err)
            body["traceback"] = traceback.format_exc()
        return jsonify(body), 500

    return app


if __name__ == "__main__":
    import socket

    port = int(os.environ.get("PORT", "0"))
    if port == 0:
        port = 5080
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
    app = create_app()
    print(f"Starting YunCe server on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
