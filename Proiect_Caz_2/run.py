from app import create_app
from waitress import serve

app = create_app()

if __name__ == '__main__':
    print("Serverul Monolitic (Caz 2) a pornit pe portul 5000...")
    serve(app, host='0.0.0.0', port=5000, threads=32)