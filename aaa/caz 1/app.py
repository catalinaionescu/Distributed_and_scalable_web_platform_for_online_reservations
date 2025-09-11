from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import bcrypt
import os
import time
from datetime import datetime, date, timedelta
from collections import defaultdict
import itertools
from waitress import serve
import socket
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = "cheie_super_secreta_perta_proiect_v6"

active_sessions = 0 # Contor pentru sesiuni active

# --- CONFIGURARE BAZĂ DE DATE ---
MASTER_DB_CONFIG = {
    'user': 'app_user',
    'password': 'parola_aplicatiei',
    'host': '192.168.50.1',
    'database': 'rezervari'
}
SLAVE_DB_CONFIG = {
    'user': 'app_user',
    'password': 'parola_aplicatiei',
    'host': '192.168.50.2',
    'database': 'rezervari'
}

db_url_master = f"mysql+pymysql://{MASTER_DB_CONFIG['user']}:{MASTER_DB_CONFIG['password']}@{MASTER_DB_CONFIG['host']}/{MASTER_DB_CONFIG['database']}?charset=utf8mb4"
db_url_slave = f"mysql+pymysql://{SLAVE_DB_CONFIG['user']}:{SLAVE_DB_CONFIG['password']}@{SLAVE_DB_CONFIG['host']}/{SLAVE_DB_CONFIG['database']}?charset=utf8mb4"

master_engine = create_engine(db_url_master, pool_size=10, max_overflow=20)
slave_engine = create_engine(db_url_slave, pool_size=10, max_overflow=20)

@contextmanager
def get_db_master_connection():
    conn = None
    try:
        conn = master_engine.connect()
        yield conn
    finally:
        if conn:
            conn.close()

# --- Funcții Helper pentru Baza de Date ---
def fetch_all(engine, query, params=None):
    with engine.connect() as cnx:
        result = cnx.execute(text(query), params or {})
        return result.mappings().all()

def fetch_one(engine, query, params=None):
    with engine.connect() as cnx:
        result = cnx.execute(text(query), params or {})
        return result.mappings().first()

def execute_commit(engine, query, params=None):
    with engine.connect() as cnx:
        result = cnx.execute(text(query), params or {})
        cnx.commit()
        if result.is_insert:
            return result.inserted_primary_key[0]
        return None


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

def get_recommendations(room_groups, requested_adults, requested_rooms_count):
    all_available_rooms = [group for group in room_groups for _ in range(int(group['count']))]
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

# --- Rutele Aplicației  ---

@app.route('/')
def home():
    try:
        logged_in = is_logged_in()
        query = "SELECT p.*, u.username FROM properties p JOIN users u ON p.owner_id = u.user_id ORDER BY p.property_id DESC LIMIT 10"
        properties = fetch_all(slave_engine, query)
        return render_template("home.html", properties=properties, logged_in=logged_in, username=session.get('username'))
    except SQLAlchemyError as e:
        print(f"Eroare la home: {e}")
        return "A apărut o eroare la încărcarea paginii principale.", 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        try:
            existing_user = fetch_one(master_engine, "SELECT user_id FROM users WHERE username = :username OR email = :email", {'username': username, 'email': email})
            if existing_user:
                flash("Numele de utilizator sau emailul există deja.", "danger")
                return redirect(url_for('register'))
            
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            execute_commit(master_engine, "INSERT INTO users (username, email, password) VALUES (:username, :email, :password)", 
                           {'username': username, 'email': email, 'password': hashed_password})
            
            flash("Contul a fost creat cu succes! Vă puteți autentifica.", "success")
            return redirect(url_for('login'))
        except SQLAlchemyError as e:
            flash(f"A apărut o eroare la înregistrare: {e}", "danger")
            return redirect(url_for('register'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            user = fetch_one(master_engine, "SELECT * FROM users WHERE username = :username", {'username': username})
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                session['is_admin'] = user.get('is_admin', 0)
                
                # Modificare: Incrementează contorul de sesiuni active
                global active_sessions
                active_sessions += 1
                
                flash('Autentificare reușită!', 'success')
                return redirect(url_for('home'))
            else:
                flash("Date de autentificare incorecte.", "danger")
        except SQLAlchemyError as e:
            flash(f"Eroare la conectare: {e}", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        global active_sessions
        active_sessions -= 1
        
    session.clear()
    flash('Deconectare reușită.', 'success')
    return redirect(url_for('home'))

@app.route('/profile')
def profile():
    if not is_logged_in(): return redirect(url_for('login'))
    if session.get('is_admin'): return redirect(url_for('admin'))
    try:
        user_id = session['user_id']
        user = fetch_one(slave_engine, "SELECT * FROM users WHERE user_id = :uid", {'uid': user_id})
        num_proprietati_data = fetch_one(slave_engine, "SELECT COUNT(*) as count FROM properties WHERE owner_id = :uid", {'uid': user_id})
        num_rezervari_active_data = fetch_one(slave_engine, "SELECT COUNT(*) as count FROM reservations WHERE user_id = :uid AND status = 'confirmed' AND end_date >= CURDATE()", {'uid': user_id})
        
        num_proprietati = num_proprietati_data['count'] if num_proprietati_data else 0
        num_rezervari_active = num_rezervari_active_data['count'] if num_rezervari_active_data else 0
        
        return render_template('profile.html', user=user, num_proprietati=num_proprietati, num_rezervari_active=num_rezervari_active, logged_in=True)
    except SQLAlchemyError as e:
        flash(f"A apărut o eroare la încărcarea profilului: {e}", "danger")
        return redirect(url_for('home'))
        
@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if not is_logged_in():
        flash("Trebuie să fii autentificat pentru a edita profilul.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_email = request.form.get('email')
        new_password = request.form.get('password')
        
        try:
            # Verifică dacă noul username sau email există deja la alt utilizator
            existing_user = fetch_one(master_engine, "SELECT user_id FROM users WHERE (username = :username OR email = :email) AND user_id != :uid", 
                                       {'username': new_username, 'email': new_email, 'uid': user_id})
            if existing_user:
                flash("Numele de utilizator sau emailul este deja folosit de un alt cont.", "danger")
                return redirect(url_for('edit_profile'))
            
            update_query = "UPDATE users SET username = :username, email = :email WHERE user_id = :uid"
            update_params = {'username': new_username, 'email': new_email, 'uid': user_id}

            if new_password:
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                update_query = "UPDATE users SET username = :username, email = :email, password = :password WHERE user_id = :uid"
                update_params['password'] = hashed_password
            
            execute_commit(master_engine, update_query, update_params)
            session['username'] = new_username # Actualizează username-ul în sesiune
            flash("Profilul a fost actualizat cu succes!", "success")
            return redirect(url_for('profile'))

        except SQLAlchemyError as e:
            flash(f"A apărut o eroare la actualizarea profilului: {e}", "danger")
            return redirect(url_for('edit_profile'))
            
    user = fetch_one(slave_engine, "SELECT * FROM users WHERE user_id = :uid", {'uid': user_id})
    if not user:
        flash("Utilizatorul nu a fost găsit.", "danger")
        return redirect(url_for('home'))

    return render_template('edit_profile.html', user=user, logged_in=True)


def check_server_status(host, port):
    # Verifică dacă un server este online la un host și port specificat
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

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'): return "Acces interzis", 403
    flask_status_html = '<span style="color: green;">Online</span>'
    iis_status_html = check_server_status('192.168.50.3', 80)
    
    # Preia datele din baza de date 
    try:
        total_users = fetch_one(slave_engine, "SELECT COUNT(*) AS total FROM users")['total']
        total_properties = fetch_one(slave_engine, "SELECT COUNT(*) AS total FROM properties")['total']
        active_reservations = fetch_one(slave_engine, "SELECT COUNT(*) AS total FROM reservations WHERE status = 'confirmed' AND end_date >= CURDATE()")['total']
        cancelled_reservations = fetch_one(slave_engine, "SELECT COUNT(*) AS total FROM reservations WHERE status = 'cancelled'")['total']
        total_rooms_count = fetch_one(slave_engine, "SELECT COUNT(*) AS total_rooms FROM rooms")['total_rooms']
        
        # Logica pentru calculul camerelor ocupate/disponibile
        ocupate, disponibile = None, None
        period = request.form.get('period')
        if period and ' to ' in period:
            try:
                start_date, end_date = [datetime.strptime(d.strip(), '%Y-%m-%d').date() for d in period.split(' to ')]
                cursor_ocupate = fetch_one(slave_engine, "SELECT COUNT(DISTINCT r.room_id) AS ocupate FROM reservations r WHERE NOT (r.end_date < :sd OR r.start_date > :ed) AND r.status = 'confirmed'", {'sd': start_date, 'ed': end_date})
                ocupate = cursor_ocupate['ocupate']
                disponibile = total_rooms_count - ocupate
            except ValueError:
                flash("Formatul perioadei selectate este invalid.", "error")

        return render_template("admin.html", 
                               flask_status=flask_status_html, 
                               iis_status=iis_status_html, 
                               total_properties=total_properties, 
                               total_users=total_users, 
                               active_sessions_count=active_sessions, 
                               active_reservations=active_reservations, 
                               cancelled_reservations=cancelled_reservations, 
                               ocupate=ocupate, 
                               disponibile=disponibile, 
                               total_rooms_count=total_rooms_count, 
                               period=period, 
                               logged_in=True)
    except Exception as e:
        print(f"Eroare la admin: {e}")
        return "Eroare panou admin", 500
    
@app.route('/my-properties')
def my_properties():
    if not is_logged_in(): return redirect('/login')
    try:
        properties = fetch_all(slave_engine, "SELECT * FROM properties WHERE owner_id = :owner_id", {'owner_id': session['user_id']})
        return render_template('my_properties.html', properties=properties, logged_in=True, username=session.get('username'))
    except SQLAlchemyError as e:
        flash(f"A apărut o eroare la afișarea proprietăților: {e}", "error")
        return redirect('/')

@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
    if not is_logged_in(): return redirect('/login')
    if request.method == 'POST':
        with master_engine.connect() as cnx:
            try:
                with cnx.begin(): # Începe o tranzacție
                    query_prop = text("INSERT INTO properties (owner_id, name, address, city, country, description) VALUES (:owner_id, :name, :address, :city, :country, '')")
                    result = cnx.execute(query_prop, {
                        'owner_id': session['user_id'], 'name': request.form['name'], 'address': request.form['address'],
                        'city': request.form['city'], 'country': request.form['country']
                    })
                    property_id = result.inserted_primary_key[0]
                    
                    room_type_names = request.form.getlist('room_type_name[]')
                    query_room = text("INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (:prop_id, :name, :cap, :price, :avail)")
                    for i in range(len(room_type_names)):
                        for _ in range(int(request.form.getlist('room_count[]')[i])):
                            cnx.execute(query_room, {
                                'prop_id': property_id, 'name': room_type_names[i], 
                                'cap': request.form.getlist('capacity[]')[i], 'price': request.form.getlist('price[]')[i],
                                'avail': "1"
                            })
                flash("Proprietatea a fost adăugată cu succes!", "success")
            except Exception as e:
                flash(f"A apărut o eroare la adăugarea proprietății: {e}", "error")
        return redirect(url_for('my_properties'))
    return render_template('add_property.html', logged_in=True, username=session.get('username'))

@app.route('/search_results', methods=['POST'])
def search_results():
    try:
        # Preluăm TOȚI parametrii din formular
        period = request.form.get('period', '').strip()
        destination = request.form.get('destination', '').strip()
        adults = request.form.get('adults', '1', type=int)
        rooms_needed = request.form.get('rooms', '1', type=int)

        if not period or ' to ' not in period:
            flash("Perioada selectată este invalidă.", "error")
            return redirect(url_for('home'))
        
        start_date, end_date = [datetime.strptime(d.strip(), '%Y-%m-%d').date() for d in period.split(' to ')]

        # Interogarea existentă este bună, dar trebuie să ne asigurăm că
        # transmitem TOȚI parametrii către template
        query = """
            SELECT DISTINCT p.property_id, p.name, p.address, p.city, p.country
            FROM properties p
            WHERE p.city LIKE :destination AND EXISTS (
                SELECT 1 FROM rooms r
                WHERE r.property_id = p.property_id AND r.available = TRUE AND r.idrooms NOT IN (
                    SELECT res.room_id FROM reservations res
                    WHERE res.status = 'confirmed' AND NOT (res.end_date <= :start_date OR res.start_date >= :end_date)
                )
            )
        """
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'destination': f"%{destination}%"
        }
        
        properties_that_match = fetch_all(slave_engine, query, params)
        
        search_params = {
            'period': period,
            'adults': adults,
            'rooms': rooms_needed
        }
        
        return render_template(
            "search_results.html", 
            properties=properties_that_match, 
            logged_in=is_logged_in(), 
            username=session.get('username'), 
            search_params=search_params  
        )
    except Exception as e:
        print(f"Database Error in search: {e}")
        return "A apărut o eroare la căutare.", 500

@app.route('/property/<int:property_id>', methods=['GET', 'POST'])
def view_property(property_id):
    try:
        prop = fetch_one(slave_engine, "SELECT p.*, u.username, p.description FROM properties p JOIN users u ON p.owner_id = u.user_id WHERE p.property_id = :prop_id", {'prop_id': property_id})
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

        total_available_rooms_data = fetch_one(slave_engine, "SELECT COUNT(idrooms) as total_rooms FROM rooms WHERE property_id = :prop_id AND available = TRUE", {'prop_id': property_id})
        total_available_rooms = total_available_rooms_data['total_rooms'] if total_available_rooms_data else 0
        
        locked_days = []
        if total_available_rooms > 0:
            bookings = fetch_all(slave_engine, "SELECT res.start_date, res.end_date FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = :prop_id AND res.status = 'confirmed' AND res.end_date >= CURDATE()", {'prop_id': property_id})
            daily_occupancy = defaultdict(int)
            for booking in bookings:
                current_day = booking['start_date']
                while current_day < booking['end_date']:
                    daily_occupancy[current_day] += 1
                    current_day += timedelta(days=1)
            for day, count in daily_occupancy.items():
                if count >= total_available_rooms:
                    locked_days.append(day.isoformat())

        room_groups_info = fetch_all(slave_engine, "SELECT name, capacity, price, COUNT(*) as count FROM rooms WHERE property_id = :prop_id GROUP BY name, capacity, price ORDER BY capacity DESC", {'prop_id': property_id})
        
        recommendations = None
        if requested_adults and requested_rooms and start_date and end_date:
            room_query = "SELECT name, capacity, price, COUNT(*) as count, GROUP_CONCAT(idrooms) as room_ids FROM rooms WHERE property_id = :prop_id AND available = TRUE AND idrooms NOT IN (SELECT room_id FROM reservations WHERE status = 'confirmed' AND NOT (end_date <= :start_date OR start_date >= :end_date)) GROUP BY name, capacity, price"
            available_room_groups = fetch_all(slave_engine, room_query, {'prop_id': property_id, 'start_date': start_date, 'end_date': end_date})
            recommendations = get_recommendations(available_room_groups, requested_adults, requested_rooms)
            if not recommendations and request.method == 'POST':
                flash("Nu s-a găsit nicio combinație pentru cerințele tale în perioada selectată.", "info")

        return render_template("view_property.html", prop=prop, room_groups_info=room_groups_info, logged_in='user_id' in session, recommendations=recommendations, requested_adults=requested_adults, requested_rooms=requested_rooms, period=period, locked_days=locked_days)
    except SQLAlchemyError as e:
        print(f"Eroare la view_property: {e}")
        flash("A apărut o eroare la încărcarea paginii proprietății.", "error")
        return redirect(url_for('home'))

@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    if 'user_id' not in session: return redirect('/login')
    
    prop = fetch_one(slave_engine, "SELECT * FROM properties WHERE property_id = :prop_id AND owner_id = :owner_id", {'prop_id': property_id, 'owner_id': session['user_id']})
    if not prop:
        flash("Acces interzis sau proprietatea nu există.", "error")
        return redirect(url_for('my_properties'))

    if request.method == 'POST':
        with master_engine.connect() as cnx:
            try:
                with cnx.begin(): # Tranzacție
                    cnx.execute(text("UPDATE properties SET name = :name, address = :address, city = :city, country = :country WHERE property_id = :prop_id"), 
                                {'name': request.form['name'], 'address': request.form['address'], 'city': request.form['city'], 'country': request.form['country'], 'prop_id': property_id})
                    
                    submitted_room_data, processed_room_types = {}, set()
                    room_type_names = request.form.getlist('room_type_name[]')
                    for i in range(len(room_type_names)):
                        name = room_type_names[i]
                        if name.strip():
                            processed_room_types.add(name)
                            submitted_room_data[name] = {'capacity': request.form.getlist('capacity[]')[i], 'price': request.form.getlist('price[]')[i], 'count': int(request.form.getlist('room_count[]')[i]), 'available': request.form.getlist('available[]')[i]}
                    
                    existing_room_types_db = {row['name']: row['current_count'] for row in fetch_all(slave_engine, "SELECT name, COUNT(idrooms) as current_count FROM rooms WHERE property_id = :prop_id GROUP BY name", {'prop_id': property_id})}

                    for name, data in submitted_room_data.items():
                        new_count, current_count = data['count'], existing_room_types_db.get(name, 0)
                        active_res_count = fetch_one(slave_engine, "SELECT COUNT(DISTINCT res.room_id) AS active_res_count FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = :prop_id AND r.name = :name AND res.status = 'confirmed' AND res.end_date >= CURDATE()", {'prop_id': property_id, 'name': name})['active_res_count']
                        if new_count < active_res_count: raise ValueError(f"Nu se poate reduce numărul de camere pentru '{name}'. Există rezervări active.")
                        if new_count > current_count:
                            for _ in range(new_count - current_count):
                                cnx.execute(text("INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (:prop_id, :name, :cap, :price, :avail)"), 
                                            {'prop_id': property_id, 'name': name, 'cap': data['capacity'], 'price': data['price'], 'avail': data['available']})
                        elif new_count < current_count:
                            rooms_to_del_count = current_count - new_count
                            rooms_to_delete = fetch_all(slave_engine, "SELECT r.idrooms FROM rooms r LEFT JOIN reservations res ON r.idrooms = res.room_id WHERE r.property_id = :prop_id AND r.name = :name AND res.reservation_id IS NULL LIMIT :limit", {'prop_id': property_id, 'name': name, 'limit': rooms_to_del_count})
                            if len(rooms_to_delete) < rooms_to_del_count: raise ValueError(f"Nu se pot șterge camere pentru '{name}'. Nu există suficiente camere fără rezervări.")
                            if rooms_to_delete:
                                cnx.execute(text("DELETE FROM rooms WHERE idrooms IN (:ids)"), {'ids': [r['idrooms'] for r in rooms_to_delete]})
                        cnx.execute(text("UPDATE rooms SET capacity = :cap, price = :price, available = :avail WHERE property_id = :prop_id AND name = :name"), 
                                    {'cap': data['capacity'], 'price': data['price'], 'avail': data['available'], 'prop_id': property_id, 'name': name})
                    
                    for name_to_delete in set(existing_room_types_db.keys()) - processed_room_types:
                        has_active_reservations = fetch_one(slave_engine, "SELECT 1 FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = :prop_id AND r.name = :name AND res.status = 'confirmed' AND res.end_date >= CURDATE() LIMIT 1", {'prop_id': property_id, 'name': name_to_delete})
                        if has_active_reservations:
                            raise ValueError(f"Tipul de cameră '{name_to_delete}' nu poate fi șters complet deoarece are rezervări active sau viitoare.")
                        cnx.execute(text("DELETE FROM rooms WHERE property_id = :prop_id AND name = :name"), {'prop_id': property_id, 'name': name_to_delete})

                flash("Proprietatea a fost actualizată cu succes!", "success")
                return redirect(url_for('my_properties'))

            except Exception as e:
                flash(f"A apărut o eroare la salvare: {e}", "error")
                return redirect(url_for('edit_property', property_id=property_id))
    
    room_groups = fetch_all(slave_engine, "SELECT name, capacity, price, available, COUNT(*) as count, GROUP_CONCAT(idrooms) as room_ids FROM rooms WHERE property_id = :prop_id GROUP BY name, capacity, price, available ORDER BY name", {'prop_id': property_id})
    return render_template("edit_property.html", prop=prop, room_groups=room_groups, logged_in=True, username=session.get('username'))

@app.route('/delete_property/<int:property_id>')
def delete_property(property_id):
    if 'user_id' not in session: return redirect('/login')
    try:
        with master_engine.connect() as cnx:
            with cnx.begin():
                prop = fetch_one(slave_engine, "SELECT owner_id FROM properties WHERE property_id = :prop_id", {'prop_id': property_id})
                if not prop or prop['owner_id'] != session['user_id']: raise ValueError("Acces interzis")
                
                has_active_res = fetch_one(slave_engine, "SELECT 1 FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = :prop_id AND res.status = 'confirmed' AND res.end_date >= CURDATE() LIMIT 1", {'prop_id': property_id})
                if has_active_res: raise ValueError("Nu puteți șterge o proprietate cu rezervări active.")
                
                res_ids = fetch_all(slave_engine, "SELECT res.reservation_id FROM reservations res JOIN rooms r ON res.room_id = r.idrooms WHERE r.property_id = :prop_id", {'prop_id': property_id})
                if res_ids:
                    res_ids_list = [r['reservation_id'] for r in res_ids]
                    cnx.execute(text("DELETE FROM reservation_details WHERE reservation_id IN :ids"), {'ids': tuple(res_ids_list)})
                    cnx.execute(text("DELETE FROM reservations WHERE reservation_id IN :ids"), {'ids': tuple(res_ids_list)})
                
                cnx.execute(text("DELETE FROM rooms WHERE property_id = :prop_id"), {'prop_id': property_id})
                cnx.execute(text("DELETE FROM properties WHERE property_id = :prop_id"), {'prop_id': property_id})
                
        flash("Proprietatea a fost ștearsă cu succes!", "success")
    except Exception as e:
        flash(f"A apărut o eroare la ștergerea proprietății: {e}", "error")
    return redirect(url_for('my_properties'))

@app.route('/cancel_reservation/<int:reservation_id>')
def cancel_reservation(reservation_id):
    if 'user_id' not in session: return redirect('/login')
    redirect_to_prop_id = request.args.get('redirect_to_prop_id', type=int)
    try:
        with master_engine.connect() as cnx:
            with cnx.begin():
                res_info = fetch_one(slave_engine, "SELECT r.user_id, r.status, rm.property_id FROM reservations r JOIN rooms rm ON r.room_id = rm.idrooms WHERE r.reservation_id = :res_id", {'res_id': reservation_id})
                if not res_info: raise ValueError("Rezervarea nu există.")
                
                owner = fetch_one(slave_engine, "SELECT owner_id FROM properties WHERE property_id = :prop_id", {'prop_id': res_info['property_id']})
                is_owner = owner and owner['owner_id'] == session['user_id']
                if not (res_info['user_id'] == session['user_id'] or is_owner): raise ValueError("Operațiune nepermisă.")
                
                if res_info['status'] == 'cancelled':
                    flash("Rezervarea este deja anulată.", "info")
                else:
                    cnx.execute(text("UPDATE reservations SET status = 'cancelled' WHERE reservation_id = :res_id"), {'res_id': reservation_id})
                    flash("Rezervarea a fost anulată cu succes!", "success")
                    
    except Exception as e:
        flash(f"A apărut o eroare la anulare: {e}", "error")
    if redirect_to_prop_id:
        return redirect(url_for('manage_property_reservations', property_id=redirect_to_prop_id))
    else:
        return redirect(url_for('my_reservations'))

@app.route('/booking/confirm', methods=['GET', 'POST'])
def booking_confirmation():
    if 'user_id' not in session: 
        return redirect(url_for('login', next=request.url))
    
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
        
        with get_db_master_connection() as conn:
            if request.method == 'POST':
                try:
                    # Verificăm din nou disponibilitatea
                    check_availability_stmt = text("""
                        SELECT idrooms FROM rooms WHERE idrooms IN :room_ids 
                        AND idrooms NOT IN (
                            SELECT room_id FROM reservations 
                            WHERE status = 'confirmed' 
                            AND NOT (end_date <= :end_date OR start_date >= :start_date)
                        )
                    """)
                    result = conn.execute(check_availability_stmt, {
                        'room_ids': room_id_list,
                        'start_date': start_date,
                        'end_date': end_date
                    })

                    available_rooms = [row[0] for row in result.fetchall()]
                    
                    if len(available_rooms) != len(room_id_list):
                        raise ValueError("Una sau mai multe camere nu mai sunt disponibile.")

                    # Obținem prețurile camerelor
                    get_prices_stmt = text("SELECT idrooms, price FROM rooms WHERE idrooms IN :room_ids")
                    result = conn.execute(get_prices_stmt, {'room_ids': room_id_list})
                    package_rooms_db = result.fetchall()

                    total_price = sum(r[1] for r in package_rooms_db) * nights
                    first_res_id = None
                    
                    # Inserăm rezervările, folosind `text()` pentru fiecare INSERT
                    insert_reservation_stmt = text("""
                        INSERT INTO reservations (user_id, room_id, start_date, end_date, status) 
                        VALUES (:user_id, :room_id, :start_date, :end_date, 'confirmed')
                    """)

                    for room in package_rooms_db:
                        result = conn.execute(insert_reservation_stmt, {
                            'user_id': session['user_id'],
                            'room_id': room[0],
                            'start_date': start_date,
                            'end_date': end_date
                        })
                        if not first_res_id: 
                            first_res_id = result.lastrowid
                    
                    if first_res_id:
                        insert_details_stmt = text("""
                            INSERT INTO reservation_details (reservation_id, full_name, phone, email, total_price) 
                            VALUES (:reservation_id, :full_name, :phone, :email, :total_price)
                        """)
                        conn.execute(insert_details_stmt, {
                            'reservation_id': first_res_id,
                            'full_name': request.form['full_name'],
                            'phone': request.form['phone'],
                            'email': request.form['email'],
                            'total_price': total_price
                        })
                    
                    conn.commit()
                    session['last_booking_id'] = first_res_id
                    return redirect(url_for('booking_success'))
                
                except SQLAlchemyError as e:
                    conn.rollback()
                    flash(f"A apărut o eroare la baza de date: {e}", "error")
                    return redirect(url_for('home'))
                except Exception as e:
                    conn.rollback()
                    flash(f"A apărut o eroare neașteptată: {e}", "error")
                    return redirect(url_for('home'))
            
            else: 
                get_rooms_stmt = text("""
                    SELECT r.*, p.name AS property_name, p.address, p.city, p.country 
                    FROM rooms r JOIN properties p ON r.property_id = p.property_id 
                    WHERE r.idrooms IN :room_ids
                """)
                result = conn.execute(get_rooms_stmt, {'room_ids': room_id_list})
                
                package_rooms = [dict(row._mapping) for row in result.fetchall()]

                if len(package_rooms) != len(room_id_list):
                    return "Una sau mai multe camere nu au fost găsite.", 404
                
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
        with get_db_master_connection() as conn:
            stmt = text("""
                SELECT res.*, r.name AS room_name, p.name AS property_name, 
                       DATEDIFF(res.end_date, res.start_date) AS nights, 
                       det.full_name, det.email, det.phone, det.total_price 
                FROM reservations res 
                JOIN rooms r ON res.room_id = r.idrooms 
                JOIN properties p ON r.property_id = p.property_id 
                LEFT JOIN reservation_details det ON det.reservation_id = res.reservation_id 
                WHERE res.reservation_id = :last_booking_id
            """)
            result = conn.execute(stmt, {'last_booking_id': last_booking_id})
            rezervare = result.fetchone()
            if not rezervare:
                flash("Nu am putut regăsi detaliile ultimei rezervări.", "error")
                return redirect(url_for('my_reservations'))
            
            rezervare_dict = dict(rezervare._mapping)
            
            return render_template("reservation_success.html", rezervare=rezervare_dict, logged_in=True)
    except Exception as e:
        flash(f"A apărut o eroare la afișarea confirmării: {e}", "error")
        return redirect(url_for('my_reservations'))

@app.route('/my-reservations')
def my_reservations():
    if 'user_id' not in session: return redirect(url_for('login', next=request.url))
    try:
        reservations = fetch_all(slave_engine, """
            SELECT r.*, ro.name AS room_name, pr.name AS property_name, 
                   det.full_name, det.phone, det.email, det.total_price 
            FROM reservations r 
            JOIN rooms ro ON r.room_id = ro.idrooms 
            JOIN properties pr ON ro.property_id = pr.property_id 
            LEFT JOIN reservation_details det ON det.reservation_id = r.reservation_id 
            WHERE r.user_id = :user_id 
            ORDER BY r.reservation_id DESC
        """, {'user_id': session['user_id']})
        return render_template('my_reservations.html', reservations=reservations, logged_in=True)
    except Exception as e:
        flash("A apărut o eroare la afișarea rezervărilor.", "error")
        return redirect('/')

@app.route('/manage_property_reservations/<int:property_id>')
def manage_property_reservations(property_id):
    if 'user_id' not in session: return redirect('/login')
    try:
        prop = fetch_one(slave_engine, "SELECT * FROM properties WHERE property_id = :prop_id AND owner_id = :owner_id", {'prop_id': property_id, 'owner_id': session['user_id']})
        if not prop:
            flash("Acces interzis sau proprietatea nu există.", "error")
            return redirect(url_for('my_properties'))
        reservations = fetch_all(slave_engine, """
            SELECT res.reservation_id, res.start_date, res.end_date, res.status, 
                   r.idrooms AS room_id, r.name AS room_name, 
                   det.full_name, det.email, det.phone, det.total_price 
            FROM reservations res 
            JOIN rooms r ON res.room_id = r.idrooms 
            LEFT JOIN reservation_details det ON res.reservation_id = det.reservation_id 
            WHERE r.property_id = :prop_id AND res.end_date >= CURDATE() 
            ORDER BY res.start_date ASC
        """, {'prop_id': property_id})
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
        prop_owner = fetch_one(slave_engine, "SELECT owner_id FROM properties WHERE property_id = :prop_id", {'prop_id': property_id})
        if not prop_owner or prop_owner['owner_id'] != session['user_id']:
            return jsonify({"can_delete_type_now": False, "message": "Acces neautorizat."}), 403
        
        has_active_reservations = fetch_one(slave_engine, """
            SELECT 1 FROM reservations res 
            JOIN rooms r ON res.room_id = r.idrooms 
            WHERE r.property_id = :prop_id AND r.name = :name 
                  AND res.status = 'confirmed' AND res.end_date >= CURDATE()
            LIMIT 1
        """, {'prop_id': property_id, 'name': room_type_name})
        
        if has_active_reservations:
            return jsonify({
                "can_delete_type_now": False,
                "message": "Acest tip de cameră nu poate fi șters deoarece are rezervări active sau viitoare."
            })
        return jsonify({
            "can_delete_type_now": True,
            "message": "Tipul de cameră poate fi șters."
        })
    except OperationalError as e:
        return jsonify({"can_delete_type_now": False, "message": f"Eroare la baza de date: {e}"}), 500

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=5000, threads=50)