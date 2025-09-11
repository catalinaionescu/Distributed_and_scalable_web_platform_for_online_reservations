from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from mysql.connector import pooling, Error as MySQLError
import bcrypt, os, time
from datetime import datetime, date, timedelta
from collections import defaultdict
import itertools
from contextlib import contextmanager
from waitress import serve
import socket 

app = Flask(__name__)
app.secret_key = "cheie_super_secreta_perta_proiect_v6"

# --- CONFIGURARE PENTRU O SINGURĂ BAZĂ DE DATE PE HOST ---

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'app_user',
    'password': 'parola_aplicatiei',
    'database': 'rezervari',
    'connection_timeout': 10
}

db_pool = None

def get_db_pool():
    global db_pool
    if db_pool is None:
        print(f"Proces [{os.getpid()}] creează pool pentru DB locală...")
        db_pool = pooling.MySQLConnectionPool(pool_name=f"local_db_{os.getpid()}", pool_size=32, **DB_CONFIG)
    return db_pool

@contextmanager
def get_db_connection():
    """Obține o conexiune de la pool-ul local pentru CITIRE și SCRIERE."""
    cnx = None
    try:
        cnx = get_db_pool().get_connection()
        yield cnx
    finally:
        if cnx: cnx.close()

@contextmanager
def get_db_cursor(cnx, dictionary=True):
    cursor = None
    try:
        cursor = cnx.cursor(dictionary=dictionary)
        yield cursor
    finally:
        if cursor: cursor.close()


def is_logged_in():
    return 'user_id' in session

def format_ro_date(value):
    if not isinstance(value, date): return value
    luni = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie"]
    return f"{value.day:02d} {luni[value.month - 1]} {value.year}"

app.jinja_env.filters['ro_date'] = format_ro_date

@app.after_request
def add_header_no_cache(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def check_server_status(host, port):
    """Verifică dacă un server este online la un host și port specificat."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            return '<span style="color: green;">Online</span>'
        else:
            return '<span style="color: red;">Offline</span>'
    except socket.gaierror:
        return '<span style="color: orange;">IP Invalid</span>'
    finally:
        sock.close()

def get_recommendations(room_groups, requested_adults, requested_rooms_count):
    all_available_rooms = [group for group in room_groups for _ in range(group['count'])]
    single_room_options = []
    for room in all_available_rooms:
        if room['capacity'] >= requested_adults:
            single_room_options.append([room])
    if single_room_options:
        valid_combinations = single_room_options
    else:
        valid_combinations = []
        max_rooms_to_check = requested_rooms_count + 1
        for i in range(2, max_rooms_to_check + 1):
            for combo in itertools.combinations(all_available_rooms, i):
                if sum(room['capacity'] for room in combo) >= requested_adults:
                    valid_combinations.append(list(combo))
    if not valid_combinations: return None
    recommendations = []
    processed_combos = set()
    for combo in valid_combinations:
        combo_key = frozenset(room['name'] for room in combo)
        processed_key = (len(combo), combo_key)
        if processed_key in processed_combos: continue
        processed_combos.add(processed_key)
        total_price = sum(room['price'] for room in combo)
        total_capacity = sum(room['capacity'] for room in combo)
        room_count = len(combo)
        score = (room_count != requested_rooms_count, total_capacity - requested_adults, total_price)
        package = {"rooms": {}, "total_price": total_price, "room_ids_to_book": [], "room_count": room_count, "sort_score": score}
        summary = {}
        temp_room_ids = {group['name']: group['room_ids'].split(',') for group in room_groups if group.get('room_ids')}
        package_room_ids = []
        is_package_valid = True
        for room in combo:
            room_name = room['name']
            if temp_room_ids.get(room_name) and temp_room_ids[room_name]:
                package_room_ids.append(temp_room_ids[room_name].pop(0))
            else:
                is_package_valid = False
                break
            if room_name not in summary:
                summary[room_name] = {'count': 0, 'capacity': room['capacity']}
            summary[room_name]['count'] += 1
        if is_package_valid:
            package['room_ids_to_book'] = package_room_ids
            package['rooms'] = summary
            recommendations.append(package)
    recommendations.sort(key=lambda x: x['sort_score'])
    return recommendations[:5]


@app.route('/')
def home():
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                logged_in = 'user_id' in session
                user_id = session.get('user_id')
                query = "SELECT p.*, u.username FROM properties p JOIN users u ON p.owner_id = u.user_id"
                params = []
                if logged_in:
                    query += " WHERE p.owner_id != %s"
                    params.append(user_id)
                query += " ORDER BY p.property_id DESC LIMIT 20"
                cursor.execute(query, tuple(params))
                all_properties = cursor.fetchall()
                today = date.today()
                tomorrow = today + timedelta(days=1)
                for prop in all_properties:
                    cursor.execute("SELECT 1 FROM rooms r WHERE r.property_id = %s AND r.available = TRUE AND r.idrooms NOT IN (SELECT res.room_id FROM reservations res WHERE res.status = 'confirmed' AND NOT (res.end_date <= %s OR res.start_date >= %s)) LIMIT 1", (prop['property_id'], today, tomorrow))
                    prop['is_available_today'] = True if cursor.fetchone() else False
                    cursor.execute("SELECT GROUP_CONCAT(DISTINCT CONCAT(rc.room_count, 'x ', rc.room_name) SEPARATOR ', ') AS room_summary FROM (SELECT name as room_name, COUNT(*) as room_count FROM rooms WHERE property_id = %s AND available = TRUE GROUP BY name) as rc", (prop['property_id'],))
                    summary = cursor.fetchone()
                    prop['room_summary'] = summary.get('room_summary') if summary else None
                all_properties.sort(key=lambda x: x.get('is_available_today', False), reverse=True)
                properties = all_properties[:10]
                return render_template("home.html", properties=properties, logged_in=logged_in, user_id=user_id, username=session.get('username'))
    except Exception as e:
        print(f"Eroare la home: {e}")
        return "A apărut o eroare la încărcarea paginii principale.", 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        try:
            with get_db_connection() as cnx:
                with get_db_cursor(cnx) as cursor:
                    cursor.execute("SELECT user_id FROM users WHERE username = %s OR email = %s", (username, email))
                    if cursor.fetchone():
                        flash("Numele de utilizator sau emailul există deja.", "danger")
                        return redirect(url_for('register'))
                    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                    cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed_password))
                    cnx.commit()
                flash("Contul a fost creat cu succes! Vă puteți autentifica.", "success")
                return redirect(url_for('login'))
        except MySQLError as e:
            flash(f"A apărut o eroare la înregistrare: {e}", "danger")
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            with get_db_connection() as cnx:
                with get_db_cursor(cnx) as cursor:
                    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                    user = cursor.fetchone()
                    if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                        session['user_id'] = user['user_id']
                        session['username'] = user['username']
                        session['is_admin'] = user.get('is_admin', 0)
                        flash('Autentificare reușită!', 'success')
                        return redirect(url_for('home'))
                    else:
                        flash("Date de autentificare incorecte.", "danger")
        except MySQLError as e:
            flash(f"Eroare la conectare: {e}", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Deconectare reușită.', 'success')
    return redirect(url_for('home'))

@app.route('/profile')
def profile():
    if not is_logged_in(): return redirect(url_for('login'))
    if session.get('is_admin'): return redirect(url_for('admin'))
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                user_id = session['user_id']
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                user = cursor.fetchone()
                cursor.execute("SELECT COUNT(*) as num_proprietati FROM properties WHERE owner_id = %s", (user_id,))
                num_proprietati = cursor.fetchone()['num_proprietati']
                cursor.execute("SELECT COUNT(*) as num_rezervari_active FROM reservations WHERE user_id = %s AND status = 'confirmed' AND end_date >= CURDATE()", (user_id,))
                num_rezervari_active = cursor.fetchone()['num_rezervari_active']
                return render_template('profile.html', user=user, num_proprietati=num_proprietati, num_rezervari_active=num_rezervari_active, logged_in=True)
    except MySQLError as e:
        flash(f"A apărut o eroare la încărcarea profilului: {e}", "danger")
        return redirect(url_for('home'))

@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session['user_id']
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                if request.method == 'POST':
                    new_username = request.form['username']
                    new_email = request.form['email']
                    current_password = request.form['current_password']
                    new_password = request.form['new_password']
                    confirm_new_password = request.form['confirm_new_password']
                    cursor.execute("SELECT password FROM users WHERE user_id = %s", (user_id,))
                    user = cursor.fetchone()
                    if not user or not bcrypt.checkpw(current_password.encode('utf-8'), user['password'].encode('utf-8')):
                        flash('Parola curentă este incorectă.', 'danger')
                        return redirect(url_for('edit_profile'))
                    cursor.execute("SELECT user_id FROM users WHERE username = %s AND user_id != %s", (new_username, user_id))
                    if cursor.fetchone():
                        flash('Acest nume de utilizator este deja folosit.', 'danger')
                        return redirect(url_for('edit_profile'))
                    cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (new_email, user_id))
                    if cursor.fetchone():
                        flash('Acest email este deja folosit.', 'danger')
                        return redirect(url_for('edit_profile'))
                    update_fields = {'username': new_username, 'email': new_email}
                    if new_password:
                        if new_password != confirm_new_password:
                            flash('Parolele noi nu se potrivesc.', 'danger')
                            return redirect(url_for('edit_profile'))
                        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                        update_fields['password'] = hashed_password
                    set_clause = ", ".join([f"{key} = %s" for key in update_fields.keys()])
                    values = tuple(update_fields.values()) + (user_id,)
                    cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = %s", values)
                    cnx.commit()
                    session['username'] = new_username
                    flash('Profilul a fost actualizat cu succes!', 'success')
                    return redirect(url_for('profile'))
                
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                user_data = cursor.fetchone()
                return render_template('edit-profile.html', user=user_data, logged_in=True)
    except MySQLError as e:
        flash(f"A apărut o eroare la baza de date: {e}", "danger")
        return redirect(url_for('profile'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'): return "Acces interzis", 403
    
    iis_status_html = check_server_status('192.168.50.3', 80)
    
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                period = request.form.get('period')
                start_date, end_date = None, None
                if period and ' to ' in period:
                    try:
                        start_date, end_date = [datetime.strptime(d.strip(), '%Y-%m-%d').date() for d in period.split(' to ')]
                    except ValueError:
                        flash("Formatul perioadei selectate este invalid.", "error")
                cursor.execute("SELECT COUNT(*) AS total FROM users"); total_users = cursor.fetchone()['total']
                cursor.execute("SELECT COUNT(*) AS total FROM properties"); total_properties = cursor.fetchone()['total']
                cursor.execute("SELECT COUNT(*) AS total FROM reservations WHERE status = 'confirmed' AND end_date >= CURDATE()"); active_reservations = cursor.fetchone()['total']
                cursor.execute("SELECT COUNT(*) AS total FROM reservations WHERE status = 'cancelled'"); cancelled_reservations = cursor.fetchone()['total']
                cursor.execute("SELECT COUNT(*) AS total_rooms FROM rooms"); total_rooms_count = cursor.fetchone()['total_rooms']
                ocupate, disponibile = None, None
                if start_date and end_date:
                    cursor.execute("SELECT COUNT(DISTINCT r.room_id) AS ocupate FROM reservations r WHERE NOT (r.end_date < %s OR r.start_date > %s) AND r.status = 'confirmed'", (start_date, end_date))
                    ocupate = cursor.fetchone()['ocupate']
                    disponibile = total_rooms_count - ocupate
                
                return render_template("admin.html", 
                                       flask_status='<span style="color: green;">Online</span>', 
                                       iis_status=iis_status_html, 
                                       total_properties=total_properties, 
                                       total_users=total_users, 
                                       active_sessions_count=len(session), 
                                       active_reservations=active_reservations, 
                                       cancelled_reservations=cancelled_reservations, 
                                       ocupate=ocupate, 
                                       disponibile=disponibile, 
                                       total_rooms_count=total_rooms_count, 
                                       period=period, 
                                       start_date=start_date, 
                                       end_date=end_date, 
                                       logged_in=True)
    except Exception as e:
        print(f"Eroare la admin: {e}")
        return "Eroare panou admin", 500

@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
    if 'user_id' not in session: return redirect('/login')
    if request.method == 'POST':
        try:
            with get_db_connection() as cnx:
                with get_db_cursor(cnx, dictionary=False) as cursor:
                    cursor.execute("INSERT INTO properties (owner_id, name, address, city, country, description) VALUES (%s, %s, %s, %s, %s, '')", (session['user_id'], request.form['name'], request.form['address'], request.form['city'], request.form['country']))
                    property_id = cursor.lastrowid
                    room_type_names = request.form.getlist('room_type_name[]')
                    for i in range(len(room_type_names)):
                        for _ in range(int(request.form.getlist('room_count[]')[i])):
                            cursor.execute("INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (%s, %s, %s, %s, %s)", (property_id, room_type_names[i], request.form.getlist('capacity[]')[i], request.form.getlist('price[]')[i], request.form.getlist('available[]')[i]))
                    cnx.commit()
            flash("Proprietatea a fost adăugată cu succes!", "success")
        except Exception as e:
            flash(f"A apărut o eroare la adăugarea proprietății: {e}", "error")
        return redirect(url_for('my_properties'))
    return render_template('add_property.html', logged_in=True, username=session.get('username'))

@app.route('/search_results', methods=['POST'])
def search_results():
    try:
        period = request.form.get('period', '').strip()
        if not period or ' to ' not in period:
            flash("Perioada selectată este invalidă.", "error")
            return redirect(url_for('home'))
        start_date, end_date = [datetime.strptime(d.strip(), '%Y-%m-%d').date() for d in period.split(' to ')]
        destination = request.form.get('destination', '').strip()
        adults = request.form.get('adults', '1', type=int)
        rooms_needed = request.form.get('rooms', '1', type=int)
        
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                base_query = "SELECT property_id, name, address, city, country, owner_id FROM properties WHERE 1=1"
                params = []
                if destination:
                    base_query += " AND (name LIKE %s OR city LIKE %s)"; params.extend([f"%{destination}%", f"%{destination}%"])
                if 'user_id' in session:
                    base_query += " AND owner_id != %s"; params.append(session['user_id'])
                
                cursor.execute(base_query, tuple(params))
                candidate_properties = cursor.fetchall()
                
                properties_that_match = []
                for prop in candidate_properties:
                    room_query = "SELECT name, capacity, price, COUNT(*) as count, GROUP_CONCAT(idrooms) as room_ids FROM rooms WHERE property_id = %s AND available = TRUE AND idrooms NOT IN (SELECT room_id FROM reservations WHERE status = 'confirmed' AND NOT (end_date <= %s OR start_date >= %s)) GROUP BY name, capacity, price"
                    cursor.execute(room_query, (prop['property_id'], start_date, end_date))
                    available_room_groups = cursor.fetchall()

                    if available_room_groups:
                        recommendation = get_recommendations(available_room_groups, adults, rooms_needed)
                        if recommendation:
                            cursor.execute("SELECT GROUP_CONCAT(DISTINCT name SEPARATOR ', ') as room_summary FROM rooms WHERE property_id = %s AND available = TRUE", (prop['property_id'],))
                            summary = cursor.fetchone()
                            prop['room_summary'] = summary.get('room_summary')
                            properties_that_match.append(prop)
                return render_template("search_results.html", properties=properties_that_match, logged_in='user_id' in session, username=session.get('username'), search_params={'period': period, 'adults': adults, 'rooms': rooms_needed})
    except Exception as e:
        print(f"Database Error in search: {e}")
        return "A apărut o eroare la căutare.", 500

@app.route('/property/<int:property_id>', methods=['GET', 'POST'])
def view_property(property_id):
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                cursor.execute("SELECT p.*, u.username, p.description FROM properties p JOIN users u ON p.owner_id = u.user_id WHERE p.property_id = %s", (property_id,))
                prop = cursor.fetchone()
                if not prop:
                    flash("Proprietatea nu a fost găsită.", "error")
                    return redirect(url_for('home'))

                source = request.form if request.method == 'POST' else request.args
                requested_adults = source.get('adults', type=int)
                requested_rooms = source.get('rooms', type=int)
                period = source.get('period', '')
                start_date, end_date = None, None
                if ' to ' in period:
                    try:
                        start_date, end_date = [datetime.strptime(d.strip(), '%Y-%m-%d').date() for d in period.split(' to ')]
                    except (ValueError, IndexError):
                        flash("Perioada selectată este invalidă.", "error")
                        period = ''

                cursor.execute("SELECT COUNT(idrooms) as total_rooms FROM rooms WHERE property_id = %s AND available = TRUE", (property_id,))
                total_available_rooms = cursor.fetchone()['total_rooms']
                locked_days = []
                if total_available_rooms > 0:
                    cursor.execute("SELECT res.start_date, res.end_date FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = %s AND res.status = 'confirmed' AND res.end_date >= CURDATE()", (property_id,))
                    bookings = cursor.fetchall()
                    daily_occupancy = defaultdict(int)
                    for booking in bookings:
                        current_day = booking['start_date']
                        while current_day < booking['end_date']:
                            daily_occupancy[current_day] += 1
                            current_day += timedelta(days=1)
                    for day, count in daily_occupancy.items():
                        if count >= total_available_rooms:
                            locked_days.append(day.isoformat())

                cursor.execute("SELECT name, capacity, price, COUNT(*) as count FROM rooms WHERE property_id = %s GROUP BY name, capacity, price ORDER BY capacity DESC", (property_id,))
                room_groups_info = cursor.fetchall()

                recommendations = None
                if requested_adults and requested_rooms and start_date and end_date:
                    room_query = "SELECT name, capacity, price, COUNT(*) as count, GROUP_CONCAT(idrooms) as room_ids FROM rooms WHERE property_id = %s AND available = TRUE AND idrooms NOT IN (SELECT room_id FROM reservations WHERE status = 'confirmed' AND NOT (end_date <= %s OR start_date >= %s)) GROUP BY name, capacity, price"
                    cursor.execute(room_query, (property_id, start_date, end_date))
                    available_room_groups = cursor.fetchall()
                    recommendations = get_recommendations(available_room_groups, requested_adults, requested_rooms)
                    if not recommendations and request.method == 'POST':
                        flash("Nu s-a găsit nicio combinație pentru cerințele tale în perioada selectată.", "info")

                return render_template("view_property.html", prop=prop, room_groups_info=room_groups_info, logged_in='user_id' in session, recommendations=recommendations, requested_adults=requested_adults, requested_rooms=requested_rooms, period=period, locked_days=locked_days)
    except Exception as e:
        print(f"Eroare la view_property: {e}")
        flash("A apărut o eroare la încărcarea paginii proprietății.", "error")
        return redirect(url_for('home'))

@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    if 'user_id' not in session: return redirect('/login')
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                cursor.execute("SELECT * FROM properties WHERE property_id = %s AND owner_id = %s", (property_id, session['user_id']))
                prop = cursor.fetchone()
                if not prop:
                    flash("Acces interzis sau proprietatea nu există.", "error")
                    return redirect(url_for('my_properties'))
                
                if request.method == 'POST':
                    try:
                        cursor.execute("UPDATE properties SET name = %s, address = %s, city = %s, country = %s WHERE property_id = %s", (request.form['name'], request.form['address'], request.form['city'], request.form['country'], property_id))
                        submitted_room_data, processed_room_types = {}, set()
                        room_type_names = request.form.getlist('room_type_name[]')
                        for i in range(len(room_type_names)):
                            name = room_type_names[i]
                            if name.strip():
                                processed_room_types.add(name)
                                submitted_room_data[name] = {'capacity': request.form.getlist('capacity[]')[i], 'price': request.form.getlist('price[]')[i], 'count': int(request.form.getlist('room_count[]')[i]), 'available': request.form.getlist('available[]')[i]}
                        cursor.execute("SELECT name, COUNT(idrooms) as current_count FROM rooms WHERE property_id = %s GROUP BY name", (property_id,))
                        existing_room_types_db = {row['name']: row['current_count'] for row in cursor.fetchall()}
                        for name, data in submitted_room_data.items():
                            new_count, current_count = data['count'], existing_room_types_db.get(name, 0)
                            cursor.execute("SELECT COUNT(DISTINCT res.room_id) AS active_res_count FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = %s AND r.name = %s AND res.status = 'confirmed' AND res.end_date >= CURDATE()", (property_id, name))
                            if new_count < cursor.fetchone()['active_res_count']: raise ValueError(f"Nu se poate reduce numărul de camere pentru '{name}'. Există rezervări active.")
                            if new_count > current_count:
                                for _ in range(new_count - current_count): cursor.execute("INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (%s, %s, %s, %s, %s)", (property_id, name, data['capacity'], data['price'], data['available']))
                            elif new_count < current_count:
                                rooms_to_del_count = current_count - new_count
                                cursor.execute("SELECT r.idrooms FROM rooms r LEFT JOIN reservations res ON r.idrooms = res.room_id WHERE r.property_id = %s AND r.name = %s AND res.reservation_id IS NULL LIMIT %s", (property_id, name, rooms_to_del_count))
                                room_ids = [row['idrooms'] for row in cursor.fetchall()]
                                if len(room_ids) < rooms_to_del_count: raise ValueError(f"Nu se pot șterge camere pentru '{name}'. Nu există suficiente camere fără rezervări.")
                                if room_ids: cursor.execute(f"DELETE FROM rooms WHERE idrooms IN ({','.join(['%s'] * len(room_ids))})", tuple(room_ids))
                            cursor.execute("UPDATE rooms SET capacity = %s, price = %s, available = %s WHERE property_id = %s AND name = %s", (data['capacity'], data['price'], data['available'], property_id, name))
                        
                        for name_to_delete in set(existing_room_types_db.keys()) - processed_room_types:
                            cursor.execute("""
                                SELECT 1 FROM reservations res
                                JOIN rooms r ON res.room_id = r.idrooms
                                WHERE r.property_id = %s AND r.name = %s
                                AND res.status = 'confirmed' AND res.end_date >= CURDATE()
                                LIMIT 1
                            """, (property_id, name_to_delete))
                            if cursor.fetchone():
                                raise ValueError(f"Tipul de cameră '{name_to_delete}' nu poate fi șters complet deoarece are rezervări active sau viitoare.")
                            
                            cursor.execute("DELETE FROM rooms WHERE property_id = %s AND name = %s", (property_id, name_to_delete))

                        cnx.commit()
                        flash("Proprietatea a fost actualizată cu succes!", "success")
                        return redirect(url_for('my_properties'))

                    except Exception as e:
                        cnx.rollback()
                        flash(f"A apărut o eroare la salvare: {e}", "error")
                        return redirect(url_for('edit_property', property_id=property_id))
                
                cursor.execute("SELECT name, capacity, price, available, COUNT(*) as count, GROUP_CONCAT(idrooms) as room_ids FROM rooms WHERE property_id = %s GROUP BY name, capacity, price, available ORDER BY name", (property_id,))
                room_groups = cursor.fetchall()
                return render_template("edit_property.html", prop=prop, room_groups=room_groups, logged_in=True, username=session.get('username'))
    except Exception as e:
        flash(f"A apărut o eroare la încărcarea paginii: {e}", "error")
        return redirect(url_for('my_properties'))

@app.route('/delete_property/<int:property_id>')
def delete_property(property_id):
    if 'user_id' not in session: return redirect('/login')
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                cursor.execute("SELECT owner_id FROM properties WHERE property_id = %s", (property_id,))
                prop = cursor.fetchone()
                if not prop or prop['owner_id'] != session['user_id']: raise ValueError("Acces interzis")
                cursor.execute("SELECT 1 FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = %s AND res.status = 'confirmed' AND res.end_date >= CURDATE() LIMIT 1", (property_id,))
                if cursor.fetchone(): raise ValueError("Nu puteți șterge o proprietate cu rezervări active.")
                cursor.execute("SELECT res.reservation_id FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = %s", (property_id,))
                res_ids = [row['reservation_id'] for row in cursor.fetchall()]
                if res_ids:
                    format_strings = ','.join(['%s'] * len(res_ids))
                    cursor.execute(f"DELETE FROM reservation_details WHERE reservation_id IN ({format_strings})", tuple(res_ids))
                    cursor.execute(f"DELETE FROM reservations WHERE reservation_id IN ({format_strings})", tuple(res_ids))
                cursor.execute("DELETE FROM rooms WHERE property_id = %s", (property_id,))
                cursor.execute("DELETE FROM properties WHERE property_id = %s", (property_id,))
                cnx.commit()
        flash("Proprietatea a fost ștearsă cu succes!", "success")
    except Exception as e:
        flash(f"A apărut o eroare la ștergerea proprietății: {e}", "error")
    return redirect(url_for('my_properties'))

@app.route('/cancel_reservation/<int:reservation_id>')
def cancel_reservation(reservation_id):
    if 'user_id' not in session: return redirect('/login')
    redirect_to_prop_id = request.args.get('redirect_to_prop_id', type=int)
    try:
        with get_db_connection() as cnx:
            with cnx.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT r.user_id, r.status, rm.property_id FROM reservations r JOIN rooms rm ON r.room_id = rm.idrooms WHERE r.reservation_id = %s", (reservation_id,))
                res_info = cursor.fetchone()
                if not res_info: raise ValueError("Rezervarea nu există.")
                cursor.execute("SELECT owner_id FROM properties WHERE property_id = %s", (res_info['property_id'],))
                owner = cursor.fetchone()
                is_owner = owner and owner['owner_id'] == session['user_id']
                if not (res_info['user_id'] == session['user_id'] or is_owner): raise ValueError("Operațiune nepermisă.")
                if res_info['status'] == 'cancelled':
                    flash("Rezervarea este deja anulată.", "info")
                else:
                    cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE reservation_id = %s", (reservation_id,))
                    cnx.commit()
                    flash("Rezervarea a fost anulată cu succes!", "success")
    except Exception as e:
        flash(f"A apărut o eroare la anulare: {e}", "error")
    if redirect_to_prop_id:
        return redirect(url_for('manage_property_reservations', property_id=redirect_to_prop_id))
    else:
        return redirect(url_for('my_reservations'))

@app.route('/booking/confirm', methods=['GET', 'POST'])
def booking_confirmation():
    if 'user_id' not in session: return redirect(url_for('login', next=request.url))
    
    source = request.form if request.method == 'POST' else request.args
    room_ids_str = source.get('ids') if request.method == 'GET' else source.get('room_ids')
    start_str = source.get('start') if request.method == 'GET' else source.get('start_date')
    end_str = source.get('end') if request.method == 'GET' else source.get('end_date')

    if not all([room_ids_str, start_str, end_str]):
        flash("Date de rezervare incomplete sau corupte.", "error")
        return redirect(url_for('home'))

    room_id_list = str(room_ids_str).split(',')

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        nights = (end_date - start_date).days
        if nights <= 0: raise ValueError("Perioadă invalidă.")

        if request.method == 'POST':
            with get_db_connection() as cnx:
                with cnx.cursor(dictionary=True) as cursor:
                    try:
                        format_strings = ','.join(['%s'] * len(room_id_list))
                        cursor.execute(f"SELECT idrooms FROM rooms WHERE idrooms IN ({format_strings}) AND idrooms NOT IN (SELECT room_id FROM reservations WHERE status = 'confirmed' AND NOT (end_date <= %s OR start_date >= %s))", tuple(room_id_list) + (start_date, end_date))
                        available_rooms = [row['idrooms'] for row in cursor.fetchall()]
                        if len(available_rooms) != len(room_id_list):
                            raise ValueError("Una sau mai multe camere nu mai sunt disponibile.")
                        
                        cursor.execute(f"SELECT idrooms, price FROM rooms WHERE idrooms IN ({format_strings})", tuple(room_id_list))
                        package_rooms_db = cursor.fetchall()
                        total_price = sum(r['price'] for r in package_rooms_db) * nights
                        first_res_id = None
                        for room in package_rooms_db:
                            cursor.execute("INSERT INTO reservations (user_id, room_id, start_date, end_date, status) VALUES (%s, %s, %s, %s, 'confirmed')", (session['user_id'], room['idrooms'], start_date, end_date))
                            if not first_res_id: first_res_id = cursor.lastrowid
                        if first_res_id:
                            cursor.execute("INSERT INTO reservation_details (reservation_id, full_name, phone, email, total_price) VALUES (%s, %s, %s, %s, %s)", (first_res_id, request.form['full_name'], request.form['phone'], request.form['email'], total_price))
                        cnx.commit()
                        session['last_booking_id'] = first_res_id
                        return redirect(url_for('booking_success'))
                    except Exception as e:
                        cnx.rollback()
                        flash(f"A apărut o eroare în timpul tranzacției: {e}", "error")
                        return redirect(url_for('home'))
        else:
            with get_db_connection() as cnx:
                with cnx.cursor(dictionary=True) as cursor:
                    format_strings = ','.join(['%s'] * len(room_id_list))
                    cursor.execute(f"SELECT r.*, p.name as property_name, p.address, p.city, p.country FROM rooms r JOIN properties p ON r.property_id = p.property_id WHERE r.idrooms IN ({format_strings})", tuple(room_id_list))
                    package_rooms = cursor.fetchall()
                    if len(package_rooms) != len(room_id_list): return "Una sau mai multe camere nu au fost găsite.", 404
                    total_price = sum(room['price'] for room in package_rooms) * nights
                    return render_template("booking_confirmation.html", package_rooms=package_rooms, start=start_date, end=end_date, total_price=total_price, nights=nights, logged_in=True)
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for('home'))
    except Exception as e:
        flash(f"A apărut o eroare neașteptată: {e}", "error")
        return redirect(url_for('home'))

@app.route('/booking/success')
def booking_success():
    if 'user_id' not in session or 'last_booking_id' not in session: return redirect(url_for('home'))
    last_booking_id = session.pop('last_booking_id', None)
    if not last_booking_id: return redirect(url_for('my_reservations'))
    try:
        with get_db_connection() as cnx:
            with cnx.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT res.*, r.name AS room_name, p.name AS property_name, 
                           DATEDIFF(res.end_date, res.start_date) AS nights, 
                           det.full_name, det.email, det.phone, det.total_price 
                    FROM reservations res 
                    JOIN rooms r ON res.room_id = r.idrooms 
                    JOIN properties p ON r.property_id = p.property_id 
                    LEFT JOIN reservation_details det ON det.reservation_id = res.reservation_id 
                    WHERE res.reservation_id = %s
                """, (last_booking_id,))
                rezervare = cursor.fetchone()
                if not rezervare:
                    flash("Nu am putut regăsi detaliile ultimei rezervări.", "error")
                    return redirect(url_for('my_reservations'))
                return render_template("reservation_success.html", rezervare=rezervare, logged_in=True)
    except Exception as e:
        flash(f"A apărut o eroare la afișarea confirmării: {e}", "error")
        return redirect(url_for('my_reservations'))

@app.route('/my-reservations')
def my_reservations():
    if 'user_id' not in session: return redirect(url_for('login', next=request.url))
    try:
        with get_db_connection() as cnx:
            with cnx.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT r.*, ro.name AS room_name, pr.name AS property_name, 
                           det.full_name, det.phone, det.email, det.total_price 
                    FROM reservations r 
                    JOIN rooms ro ON r.room_id = ro.idrooms 
                    JOIN properties pr ON ro.property_id = pr.property_id 
                    LEFT JOIN reservation_details det ON det.reservation_id = r.reservation_id 
                    WHERE r.user_id = %s 
                    ORDER BY r.reservation_id DESC
                """, (session['user_id'],))
                reservations = cursor.fetchall()
                return render_template('my_reservations.html', reservations=reservations, logged_in=True)
    except Exception as e:
        flash("A apărut o eroare la afișarea rezervărilor.", "error")
        return redirect('/')

@app.route('/my-properties')
def my_properties():
    if 'user_id' not in session: return redirect('/login')
    try:
        with get_db_connection() as cnx:
            with cnx.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM properties WHERE owner_id = %s", (session['user_id'],))
                properties = cursor.fetchall()
                return render_template('my_properties.html', properties=properties, logged_in=True, username=session.get('username'))
    except Exception as e:
        flash("A apărut o eroare la afișarea proprietăților.", "error")
        return redirect('/')

@app.route('/manage_property_reservations/<int:property_id>')
def manage_property_reservations(property_id):
    if 'user_id' not in session: return redirect('/login')
    try:
        with get_db_connection() as cnx:
            with get_db_cursor(cnx) as cursor:
                cursor.execute("SELECT * FROM properties WHERE property_id = %s AND owner_id = %s", (property_id, session['user_id']))
                prop = cursor.fetchone()
                if not prop:
                    flash("Acces interzis sau proprietatea nu există.", "error")
                    return redirect(url_for('my_properties'))
                cursor.execute("""
                    SELECT res.reservation_id, res.start_date, res.end_date, res.status, 
                           r.idrooms AS room_id, r.name AS room_name, 
                           det.full_name, det.email, det.phone, det.total_price 
                    FROM reservations res 
                    JOIN rooms r ON res.room_id = r.idrooms 
                    LEFT JOIN reservation_details det ON res.reservation_id = det.reservation_id 
                    WHERE r.property_id = %s AND res.end_date >= CURDATE() 
                    ORDER BY res.start_date ASC
                """, (property_id,))
                reservations = cursor.fetchall()
                return render_template('manage_property_reservations.html', prop=prop, reservations=reservations, logged_in=True)
    except Exception as e:
        flash(f"A apărut o eroare: {e}", "error")
        return redirect(url_for('my_properties'))

@app.route('/check_room_type_reservations/<int:property_id>/<path:room_type_name_encoded>')
def check_room_type_reservations(property_id, room_type_name_encoded):
    from urllib.parse import unquote_plus
    room_type_name = unquote_plus(room_type_name_encoded)

    if 'user_id' not in session:
        return jsonify({"can_delete_type_now": False, "message": "Autentificare necesară."}), 401
    
    try:
        with get_db_connection() as cnx:
            with cnx.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT owner_id FROM properties WHERE property_id = %s", (property_id,))
                prop_owner = cursor.fetchone()
                if not prop_owner or prop_owner['owner_id'] != session['user_id']:
                    return jsonify({"can_delete_type_now": False, "message": "Acces neautorizat."}), 403

                cursor.execute("""
                    SELECT 1 FROM reservations res 
                    JOIN rooms r ON res.room_id = r.idrooms 
                    WHERE r.property_id = %s AND r.name = %s 
                          AND res.status = 'confirmed' AND res.end_date >= CURDATE()
                    LIMIT 1
                """, (property_id, room_type_name))
                
                if cursor.fetchone():
                    return jsonify({
                        "can_delete_type_now": False,
                        "message": "Acest tip de cameră nu poate fi șters deoarece are rezervări active sau viitoare."
                    })
                
                return jsonify({
                    "can_delete_type_now": True,
                    "message": "Tipul de cameră poate fi șters."
                })

    except MySQLError as e:
        return jsonify({"can_delete_type_now": False, "message": f"Eroare la baza de date: {e}"}), 500

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=5000, threads=32)