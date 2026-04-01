from flask import Flask
from config import Config
from .utils import format_ro_date

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inregistram filtrele
    app.jinja_env.filters['ro_date'] = format_ro_date

    # Prevenim caching-ul pe pagini (dupa logout sa nu poti da back)
    @app.after_request
    def add_header_no_cache(response):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    # Inregistram rutele
    from .routes import main
    app.register_blueprint(main)

    return app