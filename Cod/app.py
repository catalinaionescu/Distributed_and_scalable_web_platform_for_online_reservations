from flask import Flask, render_template, request, redirect, session
import mysql.connector
from datetime import datetime
import bcrypt
import requests
import os
app = Flask(__name__)
app.secret_key = 'o_cheie_secreta'

# Conexiune la baza de date
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="rezervari"
)
cursor = db.cursor(dictionary=True)
@app.after_request
def add_custom_header(response):
    response.headers["X-Served-By"] = "Flask-PC"
    return response

import time

def check_health_status():
    flask_status = "Online"  # presupunem că Flask este up (fiindcă rulezi aici)
    iis_status = "Offline"   # implicit offline

    try:
        path = r"Z:\iis_health.html"  # înlocuiește cu calea ta UNC dacă e nevoie

        if os.path.exists(path):
            last_modified = os.path.getmtime(path)
            now = time.time()

            # dacă fișierul a fost actualizat în ultimele 2 minute
            if now - last_modified < 120:
                with open(path, 'r') as f:
                    content = f.read().strip().lower()
                    print("Conținut IIS health file:", content)  # debugging

                    if "online" in content:
                        iis_status = "Online"
            else:
                # fișier vechi, considerăm IIS offline
                print("Fisierul IIS health nu a fost actualizat în ultimele 2 min")
        else:
            print("Fisier IIS health nu exista:", path)

    except Exception as e:
        print("Eroare la citirea IIS health:", e)

    return flask_status, iis_status



@app.route('/', methods=['GET', 'POST'])
def home():
    search_results = None
    logged_in = 'user_id' in session
    username = session.get('username') if logged_in else None

    if request.method == 'POST':
        room_name = request.form.get('room_name')
        date_available = request.form.get('date_available')
        capacity = request.form.get('capacity')
        price = request.form.get('price')

        query = "SELECT * FROM rooms WHERE available = TRUE"
        params = []

        if room_name:
            query += " AND name LIKE %s"
            params.append(f"%{room_name}%")

        if capacity:
            try:
                capacity_int = int(capacity)
                query += " AND capacity >= %s"
                params.append(capacity_int)
            except ValueError:
                pass

        if price:
            try:
                price_float = float(price)
                query += " AND price <= %s"
                params.append(price_float)
            except ValueError:
                pass

        if date_available:
            query += """
            AND idrooms NOT IN (
                SELECT room_id FROM reservation
                WHERE %s BETWEEN start_date AND end_date
            )
            """
            params.append(date_available)

        cursor.execute(query, tuple(params))
        search_results = cursor.fetchall()

    return render_template('home.html', logged_in=logged_in, username=username, search_results=search_results)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']

            # Hash parola
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            cursor.execute(
                "INSERT INTO users (username, password, isadmin, created_at) VALUES (%s, %s, %s, NOW())",
                (username, hashed.decode('utf-8'), False)
            )
            db.commit()
            return redirect('/login')
        except Exception as e:
            return f"Eroare internă: {str(e)}"  # vezi eroarea direct
    return render_template('register.html')




# --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if user:
                stored_hash = user['password'].encode('utf-8')
                if bcrypt.checkpw(password.encode('utf-8'), stored_hash):
                    session['user_id'] = user['idusers']
                    session['username'] = user['username']
                    session['isadmin'] = user['isadmin']
                    return redirect('/')
                else:
                    error = "Parolă greșită!"
            else:
                error = "Utilizator inexistent!"
        except Exception as e:
            print("Eroare la login:", e)
            error = "Eroare internă. Încearcă din nou."

    return render_template('login.html', error=error)

 

# --------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# --------------------
from flask import abort

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect('/login')
    if session.get('isadmin'):
        return redirect('/admin')
    username = session.get('username')
    return f"Profilul lui {username}"



# --------------------
@app.route('/reserve', methods=['GET', 'POST'])
def reserve():
    if 'user_id' not in session:
        return redirect('/login')
    
    cursor.execute("SELECT * FROM rooms WHERE available = TRUE")
    rooms = cursor.fetchall()

    if request.method == 'POST':
        room_id = request.form['room_id']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        cursor.execute(
            "INSERT INTO reservation (user_id, room_id, start_date, end_date) VALUES (%s, %s, %s, %s)",
            (session['user_id'], room_id, start_date, end_date)
        )
        db.commit()
        return 'Rezervare creată cu succes'
    
    return render_template('reserve.html', rooms=rooms)

from flask import jsonify

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200


# --------------------
@app.route('/admin')
def admin():
    if not session.get('isadmin'):
        return 'Acces interzis', 403

    # Obținem statusuri
    flask_status, iis_status = check_health_status()

    cursor.execute("""
        SELECT r.*, u.username, rm.name as room_name FROM reservation r
        JOIN users u ON r.user_id = u.idusers
        JOIN rooms rm ON r.room_id = rm.idrooms
        ORDER BY r.created_at DESC
    """)
    rezervari = cursor.fetchall()

    return render_template('admin.html', rezervari=rezervari,
                           flask_status=flask_status,
                           iis_status=iis_status)



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)

