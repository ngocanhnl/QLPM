from flask import Flask

from config import Config

from .extensions import csrf, db, login_manager


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .routes.auth_routes import auth_bp
    from .routes.patient_routes import patient_bp
    from .routes.doctor_routes import doctor_bp
    from .routes.admin_routes import admin_bp
    from .routes.chatbot_routes import chatbot_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(chatbot_bp)

    with app.app_context():
        from . import models  # noqa: F401

    return app

