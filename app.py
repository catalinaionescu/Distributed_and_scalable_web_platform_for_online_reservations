from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
import bcrypt, os, time
from datetime import datetime
from datetime import timedelta
app = Flask(__name__)
app.secret_key = "o_cheie_secreta"

# Conectare MySQL
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="rezervari"
)
cursor = db.cursor(dictionary=True)


def check_health_status():
    flask_status = "Online"
    iis_status = "Offline"

    try:
        path = r"Z:\iis_health.html"  # sau orice cale reală folosești
        if os.path.exists(path):
            last_modified = os.path.getmtime(path)
            if time.time() - last_modified < 120:
                with open(path, 'r') as f:
                    if "online" in f.read().lower():
                        iis_status = "Online"
    except Exception as e:
        print("Eroare IIS check:", e)

    return flask_status, iis_status

# =====================
# RUTE PUBLICE
# =====================
from datetime import date


@app.route('/', methods=['GET', 'POST'])
def home():
    logged_in = 'user_id' in session
    user_id = session.get('user_id') if logged_in else None
    username = session.get('username') if logged_in else None
    today = date.today()

    requested_capacity = None
    name_filter = city_filter = region_filter = country_filter = None

    if request.method == 'POST':
        requested_capacity = request.form.get('capacity')
        name_filter = request.form.get('name')
        city_filter = request.form.get('city')
        region_filter = request.form.get('region')
        country_filter = request.form.get('country')

    # Construim query de bază (nu mai ieșim din funcție dacă nu s-a completat nimic!)
    query = """
        SELECT DISTINCT p.*, SUM(r.capacity) AS total_capacity
        FROM properties p
        JOIN rooms r ON r.property_id = p.property_id
        WHERE r.available = TRUE
          AND r.idrooms NOT IN (
            SELECT room_id FROM reservations
            WHERE status = 'confirmed'
              AND %s BETWEEN start_date AND end_date
          )
    """
    params = [today]

    if logged_in:
        query += " AND p.owner_id != %s"
        params.append(user_id)

    if name_filter:
        query += " AND p.name LIKE %s"
        params.append(f"%{name_filter}%")
    if city_filter:
        query += " AND p.city LIKE %s"
        params.append(f"%{city_filter}%")
    if region_filter:
        query += " AND p.city LIKE %s"
        params.append(f"%{region_filter}%")
    if country_filter:
        query += " AND p.country LIKE %s"
        params.append(f"%{country_filter}%")

    query += " GROUP BY p.property_id"

    if requested_capacity:
        query += " HAVING total_capacity >= %s"
        params.append(int(requested_capacity))

    cursor.execute(query, tuple(params))
    properties = cursor.fetchall()

    # Verificăm dacă userul are cazări proprii
    if logged_in:
        cursor.execute("SELECT COUNT(*) AS total FROM properties WHERE owner_id = %s", (user_id,))
        user_has_properties = cursor.fetchone()['total'] > 0
    else:
        user_has_properties = False

    return render_template("home.html",
                           properties=properties,
                           logged_in=logged_in,
                           username=username,
                           user_id=user_id,
                           requested_capacity=requested_capacity,
                           user_has_properties=user_has_properties)




@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt()).decode()

        cursor.execute("""
            INSERT INTO users (username, email, password)
            VALUES (%s, %s, %s)
        """, (username, email, password))
        db.commit()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    next_url = request.args.get('next')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        next_url = request.form.get('next')

        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user and bcrypt.checkpw(password.encode(), user['password'].encode()):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            return redirect(next_url or '/')
        else:
            error = "Date incorecte"

    return render_template('login.html', error=error, next=next_url)



@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# =====================
# PROFIL CLIENT
# =====================
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    username = session['username']

    if session.get('is_admin'):
        return redirect('/admin')

    # Rezervările făcute
    cursor.execute("""
        SELECT r.*, ro.name AS room_name, pr.name AS property_name
        FROM reservations r
        JOIN rooms ro ON r.room_id = ro.idrooms
        JOIN properties pr ON ro.property_id = pr.property_id
        WHERE r.user_id = %s
    """, (user_id,))
    rezervari = cursor.fetchall()

    # Proprietățile deținute
    cursor.execute("""
        SELECT * FROM properties WHERE owner_id = %s
    """, (user_id,))
    proprietati = cursor.fetchall()

    return render_template('profile.html', username=username,
                           rezervari=rezervari, proprietati=proprietati)

# =====================
# PROFIL ADMIN
# =====================
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'):
        return "Acces interzis", 403

    # Perioada selectată
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    # Număr total de proprietăți
    cursor.execute("SELECT COUNT(*) AS total FROM properties")
    total_properties = cursor.fetchone()['total']

    # Inițializăm cu None
    ocupate = disponibile = None

    if start_date and end_date:
        # Camere ocupate în perioada selectată
        cursor.execute("""
            SELECT COUNT(DISTINCT r.room_id) AS ocupate
            FROM reservations r
            WHERE NOT (r.end_date < %s OR r.start_date > %s)
            AND r.status = 'confirmed'
        """, (start_date, end_date))
        ocupate = cursor.fetchone()['ocupate']

        # Camere disponibile = toate camerele - cele ocupate
        cursor.execute("SELECT COUNT(*) AS total_rooms FROM rooms")
        total_rooms = cursor.fetchone()['total_rooms']
        disponibile = total_rooms - ocupate

    flask_status, iis_status = check_health_status()

    return render_template("admin.html",
                           flask_status=flask_status,
                           iis_status=iis_status,
                           total_properties=total_properties,
                           ocupate=ocupate,
                           disponibile=disponibile,
                           start_date=start_date,
                           end_date=end_date)

# =====================
# ADĂUGARE PROPRIETATE
# =====================
@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        # Preluare date proprietate
        name = request.form.get('name')
        address = request.form.get('address')
        city = request.form.get('city')
        region = request.form.get('region')
        country = request.form.get('country')
        owner_id = session['user_id']

        try:
       
            # Inserare proprietate
            cursor.execute("""
                INSERT INTO properties (owner_id, name, address, city, country, description)
                VALUES (%s, %s, %s, %s, %s, '')
            """, (owner_id, name, address, city, country))
            property_id = cursor.lastrowid

            # Preluare camere multiple
            room_names = request.form.getlist('room_name[]')
            capacities = request.form.getlist('capacity[]')
            prices = request.form.getlist('price[]')
            availables = request.form.getlist('available[]')

            for i in range(len(room_names)):
                cursor.execute("""
                    INSERT INTO rooms (property_id, name, capacity, price, available)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    property_id,
                    room_names[i],
                    capacities[i],
                    prices[i],
                    availables[i]
                ))

            db.commit()
            return redirect(f"/property/{property_id}")

        except Exception as e:
            db.rollback()
            return f"Eroare la salvare: {str(e)}"

    return render_template('add_property.html', logged_in='user_id' in session, username=session.get('username'))


from collections import defaultdict

@app.route('/property/<int:property_id>')
def view_property(property_id):
    logged_in = 'user_id' in session
    user_id = session.get('user_id') if logged_in else None
    username = session.get('username') if logged_in else None
    requested_capacity = request.args.get('capacity')
    today = date.today()

    cursor.execute("""
        SELECT p.*, u.username FROM properties p
        JOIN users u ON p.owner_id = u.user_id
        WHERE p.property_id = %s
    """, (property_id,))
    prop = cursor.fetchone()
    if not prop:
        return "Proprietatea nu există", 404

    cursor.execute("SELECT * FROM rooms WHERE property_id = %s", (property_id,))
    rooms = cursor.fetchall()

    # Verificăm disponibilitatea în următoarele 21 zile
    zile_disponibile = []
    for i in range(0, 21):
        zi = today + timedelta(days=i)
        cursor.execute("""
            SELECT * FROM rooms
            WHERE property_id = %s AND available = TRUE
              AND idrooms NOT IN (
                SELECT room_id FROM reservations
                WHERE status = 'confirmed'
                AND %s BETWEEN start_date AND end_date
              )
        """, (property_id, zi))
        rezultate = cursor.fetchall()
        if rezultate:
            zile_disponibile.append(zi.isoformat())

    # Obținem rezervările pe cameră
    cursor.execute("""
        SELECT room_id, start_date, end_date FROM reservations
        WHERE room_id IN (
            SELECT idrooms FROM rooms WHERE property_id = %s
        ) AND status = 'confirmed'
    """, (property_id,))
    rezervari = cursor.fetchall()

    calendar_data = defaultdict(list)
    for r in rezervari:
        current = r['start_date']
        while current <= r['end_date']:
            calendar_data[r['room_id']].append(current.isoformat())
            current += timedelta(days=1)
    calendar_data = dict(calendar_data)

    return render_template("view_property.html",
                           prop=prop,
                           rooms=rooms,
                           logged_in=logged_in,
                           username=username,
                           user_id=user_id,
                           requested_capacity=requested_capacity,
                           zile_disponibile=zile_disponibile,
                           calendar_data=calendar_data)


@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    # Verificăm dacă utilizatorul este proprietarul
    cursor.execute("SELECT * FROM properties WHERE property_id = %s AND owner_id = %s", (property_id, user_id))
    prop = cursor.fetchone()
    if not prop:
        return "Acces interzis", 403

    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        city = request.form['city']
        country = request.form['country']

        cursor.execute("""
            UPDATE properties
            SET name = %s, address = %s, city = %s, country = %s
            WHERE property_id = %s
        """, (name, address, city, country, property_id))

        room_ids = request.form.getlist('room_id[]')
        room_names = request.form.getlist('room_name[]')
        capacities = request.form.getlist('capacity[]')
        prices = request.form.getlist('price[]')
        availables = request.form.getlist('available[]')

        for i in range(len(room_ids)):
            cursor.execute("""
                UPDATE rooms SET name = %s, capacity = %s, price = %s, available = %s
                WHERE idrooms = %s AND property_id = %s
            """, (
                room_names[i],
                capacities[i],
                prices[i],
                availables[i],
                room_ids[i],
                property_id
            ))

        db.commit()
        return redirect(f"/property/{property_id}")

    # GET → încărcăm datele pentru editare
    cursor.execute("SELECT * FROM rooms WHERE property_id = %s", (property_id,))
    rooms = cursor.fetchall()

    logged_in = 'user_id' in session
    username = session.get('username') if logged_in else None

    return render_template(
        "edit_property.html",
        prop=prop,
        rooms=rooms,
        logged_in=logged_in,
        username=username
    )


@app.route('/my-properties')
def my_properties():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cursor.execute("SELECT * FROM properties WHERE owner_id = %s", (user_id,))
    properties = cursor.fetchall()

    return render_template('my_properties.html', properties=properties, logged_in=True, username=session['username'])


@app.route('/reserve/<int:room_id>', methods=['GET', 'POST'])
def reserve(room_id):
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.path))

    user_id = session['user_id']
    message = None

    # Detalii cameră
    cursor.execute("""
        SELECT r.*, p.name AS property_name
        FROM rooms r
        JOIN properties p ON r.property_id = p.property_id
        WHERE r.idrooms = %s
    """, (room_id,))
    room = cursor.fetchone()

    # Obține toate intervalele rezervate (confirmed)
    cursor.execute("""
        SELECT start_date, end_date FROM reservations
        WHERE room_id = %s AND status = 'confirmed'
    """, (room_id,))
    rezervari = cursor.fetchall()

    # Generează lista de date de evitat (toate zilele din intervalele rezervate)
    zile_indisponibile = set()
    for r in rezervari:
        start = r['start_date']
        end = r['end_date']
        current = start
        while current <= end:
            zile_indisponibile.add(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

    if request.method == 'POST':
        interval = request.form['date_range']
        try:
            start_date_str, end_date_str = interval.split(" to ")
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

            # Verificare conflict
            cursor.execute("""
                SELECT * FROM reservations
                WHERE room_id = %s AND status = 'confirmed'
                AND NOT (end_date < %s OR start_date > %s)
            """, (room_id, start_date, end_date))
            conflict = cursor.fetchone()

            if conflict:
                message = "Această cameră este deja rezervată în perioada aleasă."
            else:
                cursor.execute("""
                    INSERT INTO reservations (user_id, room_id, start_date, end_date, status)
                    VALUES (%s, %s, %s, %s, 'confirmed')
                """, (user_id, room_id, start_date, end_date))
                db.commit()
                return redirect(url_for('reservation_success', room_id=room_id))
        except:
            message = "Formatul perioadei este invalid."

    return render_template("reserve.html", room=room,
                           disabled_dates=list(zile_indisponibile),
                           message=message)


@app.route('/reservation_success')
def reservation_success():
    room_id = request.args.get('room_id')
    user_id = session.get('user_id')

    if not room_id or not user_id:
        return redirect('/')

    try:
        cursor.execute("""
            SELECT res.*, r.name AS room_name, p.name AS property_name
            FROM reservations res
            JOIN rooms r ON res.room_id = r.idrooms
            JOIN properties p ON r.property_id = p.property_id
            WHERE res.room_id = %s AND res.user_id = %s AND res.status = 'confirmed'
            ORDER BY res.reservation_id DESC
            LIMIT 1
        """, (room_id, user_id))
        rezervare = cursor.fetchone()

        if not rezervare:
            return "Rezervarea nu a fost găsită", 404

        return render_template("reservation_success.html", rezervare=rezervare)

    except Exception as e:
        return f"Eroare internă: {str(e)}", 500


@app.route('/my-reservations')
def my_reservations():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cursor.execute("""
        SELECT r.*, ro.name AS room_name, pr.name AS property_name
        FROM reservations r
        JOIN rooms ro ON r.room_id = ro.idrooms
        JOIN properties pr ON ro.property_id = pr.property_id
        WHERE r.user_id = %s
        ORDER BY r.start_date DESC
    """, (user_id,))
    reservations = cursor.fetchall()

    return render_template('my_reservations.html', reservations=reservations, logged_in=True, username=session['username'])


@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    if request.method == 'POST':
        new_username = request.form['username']
        new_email = request.form['email']

        cursor.execute("UPDATE users SET username = %s, email = %s WHERE user_id = %s",
                       (new_username, new_email, user_id))
        db.commit()
        session['username'] = new_username
        return redirect('/profile')

    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    return render_template("edit_profile.html", user=user, logged_in=True, username=session['username'])


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)