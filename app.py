"""
MyBookApps — 科幻写作助手 Web 应用入口
Flask API 后端 + React SPA 静态服务（生产模式）
"""
import sys
import os

# 将项目根添加到 path，以便导入 knowledge_rag
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory
from app_config import DB_PATH, SECRET_KEY, MAX_CONTENT_LENGTH, UPLOAD_FOLDER, MYBOOKAPPS_ROOT
from database import db
from logger import init_app_logging, get_logger

log = get_logger("app")


def create_app():
    app = Flask(__name__, static_folder=None)

    # ---- 日志系统 ----
    init_app_logging(app)
    log.info("=" * 50)
    log.info("  📚 MyBookApps 启动中...")
    log.info("=" * 50)


def create_app():
    app = Flask(__name__, static_folder=None)

    # ---- 基础配置 ----
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

    # ---- 初始化数据库 ----
    db.init_app(app)
    with app.app_context():
        db.create_all()
        log.info(f"  数据库: {DB_PATH}")

    # ---- CORS 支持（开发模式 Vite 跨域）----
    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    # ---- 注册 API 蓝图 ----
    from routes.api_upload import api_upload_bp
    from routes.api_ideas import api_ideas_bp
    from routes.api_outlines import api_outlines_bp
    from routes.api_writing import api_writing_bp
    from routes.api_rewrite import api_rewrite_bp
    from routes.api_storyboard import api_storyboard_bp

    app.register_blueprint(api_upload_bp, url_prefix="/api")
    app.register_blueprint(api_ideas_bp, url_prefix="/api")
    app.register_blueprint(api_outlines_bp, url_prefix="/api")
    app.register_blueprint(api_writing_bp, url_prefix="/api")
    app.register_blueprint(api_rewrite_bp, url_prefix="/api")
    app.register_blueprint(api_storyboard_bp, url_prefix="/api")

    # ---- React SPA 静态服务（生产模式）----
    frontend_dist = os.path.join(MYBOOKAPPS_ROOT, "frontend", "dist")
    if os.path.exists(frontend_dist):
        @app.route("/")
        @app.route("/<path:path>")
        def serve_spa(path="index.html"):
            """服务 React SPA：API 之外的请求全部返回前端"""
            if path.startswith("api/"):
                return {"error": "Not found"}, 404
            file_path = os.path.join(frontend_dist, path)
            if os.path.isfile(file_path):
                return send_from_directory(frontend_dist, path)
            return send_from_directory(frontend_dist, "index.html")
    else:
        @app.route("/")
        def dev_notice():
            return """
            <div style="font-family:sans-serif;text-align:center;padding:60px 20px">
              <h2>🚀 MyBookApps API 已启动</h2>
              <p>前端请通过 Vite 开发服务器访问：</p>
              <a href="http://localhost:5173" style="color:#6366f1;font-size:18px">http://localhost:5173</a>
              <p style="color:#888;margin-top:20px">API 地址: <code>/api/*</code></p>
            </div>
            """

    return app


if __name__ == "__main__":
    app = create_app()
    print("\n" + "=" * 50)
    print("  📚 MyBookApps — 科幻写作助手")
    print("  API:  http://localhost:5000/api")
    print("  前端: http://localhost:5173 (npm run dev)")
    print("=" * 50 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
