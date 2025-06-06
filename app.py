from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify # Added jsonify here
from mysql.connector import pooling, Error as MySQLError
import bcrypt, os, time
from datetime import datetime, date, timedelta
from collections import defaultdict
import itertools

app = Flask(__name__)
app.secret_key = "cheie_super_secreta_perta_proiect_v6"

db_pool = pooling.MySQLConnectionPool(
    pool_name="rezervari_pool_v5",
    pool_size=5,
    host="localhost",
    user="root",
    password="",
    database="rezervari"
)

def is_logged_in():
    return 'user_id' in session

def format_ro_date(value):
    if not isinstance(value, date):
        return value
    luni = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
            "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie"]
    return f"{value.day:02d} {luni[value.month - 1]} {value.year}"

app.jinja_env.filters['ro_date'] = format_ro_date


def parse_romanian_date(date_str):
    """Functie care traduce luna din romana in engleza si parseaza data."""
    if not date_str: return None

    ro_to_en_months = {
        'ianuarie': 'January', 'februarie': 'February', 'martie': 'March', 'aprilie': 'April',
        'mai': 'May', 'iunie': 'June', 'iulie': 'July', 'august': 'August',
        'septembrie': 'September', 'octombrie': 'October', 'noiembrie': 'November', 'decembrie': 'December'
    }

    date_str_lower = date_str.strip().lower()
    for ro_month, en_month in ro_to_en_months.items():
        if ro_month in date_str_lower:
            date_str_lower = date_str_lower.replace(ro_month, en_month)
            try:
                return datetime.strptime(date_str_lower, '%d %B %Y').date()
            except ValueError:
                return None
    return None

@app.template_filter('ro_date')
def format_ro_date_filter(value):
    """Filtru Jinja pentru a formata data in stil romanesc in template-uri."""
    if not isinstance(value, (date, datetime)):
        return value
    luni = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
            "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie"]
    return f"{value.day:02d} {luni[value.month - 1]} {value.year}"


@app.after_request
def add_header_no_cache(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
def find_first_available_date(cursor, property_id):
    try:
        cursor.execute("""
            SELECT res.start_date, res.end_date FROM reservations res
            JOIN rooms r ON res.room_id = r.idrooms
            WHERE r.property_id = %s AND res.status = 'confirmed' AND res.end_date >= CURDATE()
            ORDER BY res.start_date ASC
        """, (property_id,))
        bookings = cursor.fetchall()
        if not bookings:
            cursor.execute("SELECT 1 FROM rooms WHERE property_id = %s AND available = TRUE LIMIT 1", (property_id,))
            return date.today() + timedelta(days=1) if cursor.fetchone() else None
        last_end_date = date.today()
        if bookings[0]['start_date'] > last_end_date + timedelta(days=1):
            return last_end_date + timedelta(days=1)
        last_end_date = bookings[0]['end_date']
        for i in range(1, len(bookings)):
            if bookings[i]['start_date'] > last_end_date + timedelta(days=1): return last_end_date + timedelta(days=1)
            if bookings[i]['end_date'] > last_end_date: last_end_date = bookings[i]['end_date']
        return last_end_date + timedelta(days=1)
    except MySQLError as e:
        print(f"Eroare în find_first_available_date: {e}")
        return None

def get_recommendations(room_groups, requested_adults, requested_rooms_count):
    all_available_rooms = [group for group in room_groups for _ in range(group['count'])]
    valid_combinations = []

    # Cautam combinatii folosind pana la numarul de camere cerut + 1 (pentru flexibilitate)
    # Exemplu: daca se cer 2 camere, cautam pachete de 1, 2 si 3 camere.
    max_rooms_to_check = requested_rooms_count + 1

    for i in range(1, max_rooms_to_check + 1):
        for combo in itertools.combinations(all_available_rooms, i):
            if sum(room['capacity'] for room in combo) >= requested_adults:
                valid_combinations.append(list(combo))

    if not valid_combinations: return None

    recommendations = []
    processed_combos = set()

    for combo in valid_combinations:
        # Folosim un 'frozenset' pentru a ne asigura ca o combinatie de camere (ex: [Dubla, Tripla])
        # este tratata la fel ca [Tripla, Dubla] si nu apare de mai multe ori.
        combo_key = frozenset(room['name'] for room in combo)

        # Verificam daca am procesat deja o combinatie identica de tipuri de camere cu acelasi numar de camere
        if (len(combo), combo_key) in processed_combos: continue
        processed_combos.add((len(combo), combo_key))

        total_price = sum(room['price'] for room in combo)
        total_capacity = sum(room['capacity'] for room in combo)
        room_count = len(combo)

        # Scorul de sortare imbunatatit:
        # 1. Prioritizeaza pachetele care au exact numarul de camere cerut.
        # 2. Apoi, prioritizeaza pachetele care au cea mai mica risipa de spatiu (capacitate totala - adulti).
        # 3. La final, sorteaza dupa pretul cel mai mic.
        score = (room_count != requested_rooms_count, total_capacity - requested_adults, total_price)

        package = {
            "rooms": {},
            "total_price": total_price,
            "room_ids_to_book": [],
            "room_count": room_count,
            "sort_score": score
        }

        summary = {}
        # Creăm o copie a ID-urilor disponibile pentru a le putea consuma
        temp_room_ids = {group['name']: group['room_ids'].split(',') for group in room_groups if group['room_ids']}

        for room in combo:
            # Alegem un ID de camera unic pentru rezervare
            if temp_room_ids.get(room['name']):
                package["room_ids_to_book"].append(temp_room_ids[room['name']].pop(0))

            if room['name'] not in summary:
                summary[room['name']] = {'count': 0, 'capacity': room['capacity']}
            summary[room['name']]['count'] += 1

        package['rooms'] = summary
        recommendations.append(package)

    # Sortam toate recomandarile gasite dupa scorul calculat
    recommendations.sort(key=lambda x: x['sort_score'])

    # **MODIFICARE CHEIE: Returnam doar cele mai bune 5 rezultate**
    return recommendations[:5]

@app.route('/')
def home():
    logged_in = 'user_id' in session
    user_id = session.get('user_id')
    properties = []
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        # Pasul 1: Preluăm o listă de bază cu proprietăți recente
        query = "SELECT p.*, u.username FROM properties p JOIN users u ON p.owner_id = u.user_id"
        params = []
        if logged_in:
            query += " WHERE p.owner_id != %s"
            params.append(user_id)
        query += " ORDER BY p.property_id DESC LIMIT 20" # Preluăm mai multe ca să avem de unde alege

        cursor.execute(query, tuple(params))
        all_properties = cursor.fetchall()

        today = date.today()
        tomorrow = today + timedelta(days=1)

        # Pasul 2: Iterăm prin fiecare proprietate și o "îmbogățim" cu date
        for prop in all_properties:
            # Verificăm dacă are măcar o cameră liberă pentru o noapte începând de azi
            cursor.execute("""
                SELECT 1 FROM rooms r WHERE r.property_id = %s AND r.available = TRUE AND r.idrooms NOT IN (
                    SELECT res.room_id FROM reservations res WHERE res.status = 'confirmed' AND NOT (res.end_date <= %s OR res.start_date >= %s)
                ) LIMIT 1
            """, (prop['property_id'], today, tomorrow))

            prop['is_available_today'] = True if cursor.fetchone() else False

            # Generăm sumarul de camere, indiferent de disponibilitate
            cursor.execute("""
                SELECT GROUP_CONCAT(DISTINCT CONCAT(rc.room_count, 'x ', rc.room_name) SEPARATOR ', ') AS room_summary
                FROM (
                    SELECT name as room_name, COUNT(*) as room_count FROM rooms
                    WHERE property_id = %s AND available = TRUE GROUP BY name
                ) as rc
            """, (prop['property_id'],))
            summary = cursor.fetchone()
            prop['room_summary'] = summary.get('room_summary') if summary else None

        # Pasul 3: Sortăm lista în Python și luăm primele 10
        all_properties.sort(key=lambda x: x.get('is_available_today', False), reverse=True)
        properties = all_properties[:10]

    except MySQLError as e:
        print(f"Eroare la home: {e}")
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    return render_template("home.html", properties=properties, logged_in=logged_in, user_id=user_id, username=session.get('username'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    next_url = request.args.get('next') or ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cnx, cursor = None, None
        try:
            cnx = db_pool.get_connection()
            cursor = cnx.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if user and bcrypt.checkpw(password.encode(), user['password'].encode()):
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                session['is_admin'] = user['is_admin']
                return redirect(request.form.get('next') or '/')
            else:
                error = "Date de autentificare incorecte."
        except MySQLError as e:
            error = f"Eroare la conectare: {e}"
        finally:
            if cursor: cursor.close()
            if cnx: cnx.close()

    return render_template('login.html', error=error, next=next_url)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect('/login')
    if session.get('is_admin'): return redirect('/admin')

    user_id = session['user_id']
    rezervari, proprietati = [], []
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        cursor.execute("SELECT r.*, ro.name AS room_name, pr.name AS property_name FROM reservations r JOIN rooms ro ON r.room_id = ro.idrooms JOIN properties pr ON ro.property_id = pr.property_id WHERE r.user_id = %s ORDER BY r.start_date DESC", (user_id,))
        rezervari = cursor.fetchall()
        cursor.execute("SELECT * FROM properties WHERE owner_id = %s", (user_id,))
        proprietati = cursor.fetchall()
    except MySQLError as e:
        print(f"Eroare la profil: {e}")
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    return render_template('profile.html', username=session.get('username'), rezervari=rezervari, proprietati=proprietati, logged_in='user_id' in session)


# You will need to implement this function yourself or remove its call if IIS is not set up
def check_health_status():
    # Placeholder for checking Flask health
    flask_status = "Online"
    # Placeholder for checking IIS health
    iis_status = "Offline (not implemented)"
    try:
        # If you have a way to check IIS, implement it here.
        # For example, if IIS hosts a specific health endpoint.
        # import requests
        # response = requests.get("http://your_iis_server_ip/health_check")
        # if response.status_code == 200:
        #    iis_status = "Online"
        pass
    except Exception as e:
        print(f"Eroare checking IIS health: {e}")
        iis_status = f"Eroare: {e}"
    return flask_status, iis_status

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'):
        return "Acces interzis", 403

    # Initialize period and dates for the form
    period = request.form.get('period')
    start_date, end_date = None, None

    # Parse period if provided by Litepicker
    if period and ' to ' in period:
        try:
            start_date, end_date = [datetime.strptime(d.strip(), '%Y-%m-%d').date() for d in period.split(' to ')]
        except ValueError:
            flash("Formatul perioadei selectate este invalid.", "error")
            start_date, end_date = None, None # Reset if parsing fails

    ocupate, disponibile, total_rooms_count = None, None, None

    # New stats variables
    total_users = 0
    active_sessions_count = len(session) # Simplified: count entries in session, assuming user_id exists
    total_properties = 0
    active_reservations = 0
    cancelled_reservations = 0

    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        # Fetch new statistics
        cursor.execute("SELECT COUNT(*) AS total FROM users")
        total_users = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM properties")
        total_properties = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM reservations WHERE status = 'confirmed' AND end_date >= CURDATE()")
        active_reservations = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM reservations WHERE status = 'cancelled'")
        cancelled_reservations = cursor.fetchone()['total']

        # Original room occupancy statistics
        if start_date and end_date:
            cursor.execute("SELECT COUNT(DISTINCT r.room_id) AS ocupate FROM reservations r WHERE NOT (r.end_date < %s OR r.start_date > %s) AND r.status = 'confirmed'", (start_date, end_date))
            ocupate = cursor.fetchone()['ocupate']
            cursor.execute("SELECT COUNT(*) AS total_rooms FROM rooms")
            total_rooms_count = cursor.fetchone()['total_rooms']
            disponibile = total_rooms_count - ocupate
        else:
            # If no dates are selected, still get total_rooms_count for general stats
            cursor.execute("SELECT COUNT(*) AS total_rooms FROM rooms")
            total_rooms_count = cursor.fetchone()['total_rooms']


    except MySQLError as e:
        print(f"Eroare la admin: {e}")
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    flask_status, iis_status = check_health_status()
    # Explicitly set logged_in to True/False based on session.get('user_id')
    is_user_logged_in = True if session.get('user_id') else False
    return render_template("admin.html",
                           flask_status=flask_status,
                           iis_status=iis_status,
                           total_properties=total_properties,
                           total_users=total_users,
                           active_sessions_count=active_sessions_count,
                           active_reservations=active_reservations,
                           cancelled_reservations=cancelled_reservations,
                           ocupate=ocupate,
                           disponibile=disponibile,
                           total_rooms_count=total_rooms_count, # Pass this too
                           period=period, # Pass period back to retain selection in datepicker
                           start_date=start_date, # Pass parsed dates for display in results section
                           end_date=end_date,
                           logged_in=is_user_logged_in) # Pass the explicit boolean value



@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
    if 'user_id' not in session: return redirect('/login')
    if request.method == 'POST':
        cnx, cursor = None, None
        try:
            cnx = db_pool.get_connection()
            cursor = cnx.cursor()
            cnx.start_transaction()

            cursor.execute("INSERT INTO properties (owner_id, name, address, city, country, description) VALUES (%s, %s, %s, %s, %s, '')",
                           (session['user_id'], request.form['name'], request.form['address'], request.form['city'], request.form['country']))
            property_id = cursor.lastrowid

            room_type_names = request.form.getlist('room_type_name[]')
            capacities = request.form.getlist('capacity[]')
            prices = request.form.getlist('price[]')
            room_counts = request.form.getlist('room_count[]')
            availabilities = request.form.getlist('available[]')

            for i in range(len(room_type_names)):
                for _ in range(int(room_counts[i])):
                    cursor.execute("INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (%s, %s, %s, %s, %s)",
                                   (property_id, room_type_names[i], capacities[i], prices[i], availabilities[i]))

            cnx.commit()
            return redirect(url_for('my_properties'))
        except MySQLError as e:
            if cnx: cnx.rollback()
            flash(f"A apărut o eroare la adăugarea proprietății: {e}", "error")
        finally:
            if cursor: cursor.close()
            if cnx: cnx.close()
    return render_template('add_property.html', logged_in='user_id' in session, username=session.get('username'))

@app.route('/search_results', methods=['POST'])
def search_results():
    logged_in = 'user_id' in session
    user_id = session.get('user_id')
    destination = request.form.get('destination', '').strip()
    period = request.form.get('period', '').strip()
    adults = request.form.get('adults', '1', type=int)
    rooms_needed = request.form.get('rooms', '1', type=int)

    start_date, end_date = None, None
    if ' to ' in period:
        try:
            start_date, end_date = [datetime.strptime(d.strip(), '%Y-%m-%d').date() for d in period.split(' to ')]
        except (ValueError, IndexError):
            flash("Perioada selectată este invalidă.", "error")
            return redirect(url_for('home'))

    if not start_date:
        flash("Te rugăm să selectezi o perioadă pentru căutare.", "error")
        return redirect(url_for('home'))

    cnx, cursor = None, None
    properties_that_match = []
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        base_query = "SELECT property_id, name, address, city, country, owner_id FROM properties WHERE 1=1"
        params = []
        if destination:
            base_query += " AND (name LIKE %s OR city LIKE %s)"
            params.extend([f"%{destination}%", f"%{destination}%"])
        if logged_in:
            base_query += " AND owner_id != %s"
            params.append(user_id)

        cursor.execute(base_query, tuple(params))
        candidate_properties = cursor.fetchall()

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
    except MySQLError as e:
        print(f"Database Error in search: {e}")
        return "A apărut o eroare la căutare.", 500
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    search_params = {'period': period, 'adults': adults, 'rooms': rooms_needed}
    return render_template("search_results.html", properties=properties_that_match, logged_in='user_id' in session, user_id=user_id,
                           username=session.get('username'), search_params=search_params)


@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    if 'user_id' not in session: return redirect('/login')

    cnx, cursor = None, None
    try: # Outer try block for database connection
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        # Verificăm dacă proprietatea aparține utilizatorului
        cursor.execute("SELECT * FROM properties WHERE property_id = %s AND owner_id = %s", (property_id, session['user_id']))
        prop = cursor.fetchone()
        if not prop:
            return "Acces interzis sau proprietatea nu există.", 403

        if request.method == 'POST':
            # --- Logica de Salvare (POST) ---

            # 1. Verificăm dacă există rezervări viitoare confirmate pentru această proprietate
            # This check applies to ANY change that might affect reserved rooms
            cursor.execute("""
                SELECT COUNT(*) as res_count FROM reservations res
                JOIN rooms r ON res.room_id = r.idrooms
                WHERE r.property_id = %s AND res.status = 'confirmed' AND res.end_date >= CURDATE()
            """, (property_id,))

            if cursor.fetchone()['res_count'] > 0:
                # If there are any active reservations, we need more granular checks
                # We will prevent wholesale deletion or reduction below active reservations
                pass # The more specific checks are within the inner try-except
            
            # Get existing room types in DB for comparison
            cursor.execute("SELECT name, COUNT(idrooms) as current_count FROM rooms WHERE property_id = %s GROUP BY name", (property_id,))
            existing_room_types_db = {row['name']: row['current_count'] for row in cursor.fetchall()}

            try: # Inner try block for transaction
                cnx.start_transaction()

                # Update property details
                cursor.execute("UPDATE properties SET name = %s, address = %s, city = %s, country = %s WHERE property_id = %s",
                               (request.form['name'], request.form['address'], request.form['city'], request.form['country'], property_id))

                submitted_room_type_names = request.form.getlist('room_type_name[]')
                submitted_capacities = request.form.getlist('capacity[]')
                submitted_prices = request.form.getlist('price[]')
                submitted_room_counts = request.form.getlist('room_count[]')
                submitted_availabilities = request.form.getlist('available[]')

                processed_room_types = set() # To track which types were processed from form

                # Iterate through submitted room types to update existing or add new ones
                for i in range(len(submitted_room_type_names)):
                    name = submitted_room_type_names[i]
                    capacity = submitted_capacities[i]
                    price = submitted_prices[i]
                    new_count = int(submitted_room_counts[i])
                    available = submitted_availabilities[i]

                    if not name.strip(): # Skip empty entries
                        continue
                    processed_room_types.add(name)

                    # Get active reservations for this specific room type
                    cursor.execute("""
                        SELECT COUNT(res.reservation_id) AS active_res_count
                        FROM reservations res
                        JOIN rooms r ON res.room_id = r.idrooms
                        WHERE r.property_id = %s AND r.name = %s
                        AND res.status = 'confirmed' AND res.end_date >= CURDATE()
                    """, (property_id, name))
                    active_res_count_for_type = cursor.fetchone()['active_res_count']

                    current_count_in_db = existing_room_types_db.get(name, 0)

                    # Validation for reducing room count
                    if new_count < active_res_count_for_type:
                        raise ValueError(f"Nu se poate reduce numărul de camere pentru '{name}' la {new_count}. Există {active_res_count_for_type} rezervări active pentru acest tip.")

                    # Delete existing rooms of this type to re-insert with new count/details
                    cursor.execute("DELETE FROM rooms WHERE property_id = %s AND name = %s", (property_id, name))

                    # Re-insert rooms based on the new count
                    for _ in range(new_count):
                        cursor.execute("INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (%s, %s, %s, %s, %s)",
                                       (property_id, name, capacity, price, available))

                # Handle deletions of room types that were removed from the form
                for existing_name in existing_room_types_db:
                    if existing_name not in processed_room_types:
                        # Check if this type has active reservations before deleting
                        cursor.execute("""
                            SELECT COUNT(res.reservation_id) AS active_res_count
                            FROM reservations res
                            JOIN rooms r ON res.room_id = r.idrooms
                            WHERE r.property_id = %s AND r.name = %s
                            AND res.status = 'confirmed' AND res.end_date >= CURDATE()
                        """, (property_id, existing_name))
                        active_res_count_for_deleted_type = cursor.fetchone()['active_res_count']

                        if active_res_count_for_deleted_type > 0:
                            raise ValueError(f"Nu se poate șterge tipul de cameră '{existing_name}'. Există {active_res_count_for_deleted_type} rezervări active pentru acest tip.")
                        
                        # If no active reservations, proceed to delete rooms of this type
                        cursor.execute("DELETE FROM rooms WHERE property_id = %s AND name = %s", (property_id, existing_name))

                cnx.commit()
                flash("Proprietatea a fost actualizată cu succes!", "success")
                return redirect(url_for('my_properties'))

            except MySQLError as e: # Inner except for transaction errors
                if cnx: cnx.rollback()
                flash(f"A apărut o eroare la salvare: {e}", "error")
                return redirect(url_for('edit_property', property_id=property_id))
            except ValueError as e: # Catch validation errors (e.g., trying to reduce count below active reservations)
                if cnx: cnx.rollback()
                flash(f"Eroare de validare: {e}", "error")
                return redirect(url_for('edit_property', property_id=property_id))

        # --- Logica pentru afișarea paginii (GET) ---
        cursor.execute("""
            SELECT name, capacity, price, available, COUNT(*) as count,
                   GROUP_CONCAT(idrooms) as room_ids
            FROM rooms
            WHERE property_id = %s
            GROUP BY name, capacity, price, available
            ORDER BY name
        """, (property_id,))
        room_groups = cursor.fetchall()

        return render_template("edit_property.html", prop=prop, room_groups=room_groups, logged_in='user_id' in session, username=session.get('username'))

    except MySQLError as e: # Outer except for database connection errors
        flash(f"A apărut o eroare la încărcarea paginii de editare: {e}", "error")
        return redirect(url_for('my_properties'))
    finally: # Outer finally to ensure cursor and connection are closed
        if cursor: cursor.close()
        if cnx: cnx.close()


# NEW AJAX ROUTE: Check for active reservations for a room type
@app.route('/check_room_type_reservations/<int:property_id>/<path:room_type_name_encoded>')
def check_room_type_reservations(property_id, room_type_name_encoded):
    from urllib.parse import unquote_plus # Import unquote_plus
    room_type_name = unquote_plus(room_type_name_encoded) # Decode the room type name

    if 'user_id' not in session:
        return jsonify({"has_reservations": False, "message": "Unauthorized"}), 401 # Or redirect to login

    cnx, cursor = None, None
    has_reservations = False
    message = ""
    total_rooms_of_type = 0
    active_reservations_of_type = 0
    can_delete_type_now = False # Can delete if 0 active reservations

    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        # First, verify ownership of the property
        cursor.execute("SELECT owner_id FROM properties WHERE property_id = %s", (property_id,))
        prop_owner = cursor.fetchone()
        if not prop_owner or prop_owner['owner_id'] != session['user_id']:
            return jsonify({"has_reservations": False, "message": "Access denied"}), 403

        # Count total rooms of this type
        cursor.execute("SELECT COUNT(idrooms) AS total_count FROM rooms WHERE property_id = %s AND name = %s", (property_id, room_type_name))
        total_rooms_of_type = cursor.fetchone()['total_count']

        # Count active/future confirmed reservations for any room of this type in this property
        cursor.execute("""
            SELECT COUNT(res.reservation_id) AS active_res_count
            FROM reservations res
            JOIN rooms r ON res.room_id = r.idrooms
            WHERE r.property_id = %s
            AND r.name = %s  -- Match by room type name
            AND res.status = 'confirmed'
            AND res.end_date >= CURDATE()
        """, (property_id, room_type_name))
        
        active_reservations_of_type = cursor.fetchone()['active_res_count']
        
        if active_reservations_of_type > 0:
            has_reservations = True
            if active_reservations_of_type == total_rooms_of_type:
                message = f"Acest tip de cameră ('{room_type_name}') are {active_reservations_of_type} rezervări active. Toate camerele de acest tip sunt rezervate și nu pot fi șterse."
            else:
                message = f"Acest tip de cameră ('{room_type_name}') are {active_reservations_of_type} rezervări active dintr-un total de {total_rooms_of_type} camere. Nu poate fi șters complet cât timp există rezervări active."
            can_delete_type_now = False
        else:
            message = f"Nicio rezervare activă pentru tipul de cameră '{room_type_name}'. Poate fi șters."
            can_delete_type_now = True

    except MySQLError as e:
        print(f"Eroare la verificare rezervari tip camera: {e}")
        return jsonify({"has_reservations": False, "message": "Database error", "error_details": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()
    
    return jsonify({
        "has_reservations": has_reservations,
        "message": message,
        "total_rooms_of_type": total_rooms_of_type,
        "active_reservations_of_type": active_reservations_of_type,
        "can_delete_type_now": can_delete_type_now
    })


@app.route('/property/<int:property_id>', methods=['GET', 'POST'])
def view_property(property_id):
    logged_in = 'user_id' in session
    prop, room_groups_info, recommendations, locked_days = None, [], None, []

    # Pas 1: Unificam preluarea datelor, indiferent daca e GET (din link) sau POST (din formular)
    source = request.args if request.method == 'GET' else request.form

    requested_adults = source.get('adults', type=int)
    requested_rooms = source.get('rooms', type=int)

    period = ''
    start_str, end_str = None, None

    if request.method == 'POST':
        period = source.get('period', '')
        if ' to ' in period:
            start_str, end_str = period.split(' to ', 1)
    else: # GET
        start_str = source.get('start')
        end_str = source.get('end')
        if start_str and end_str:
            period = f"{start_str} to {end_str}"

    # --- Incepe logica de procesare ---
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        cursor.execute("SELECT p.*, u.username, p.description FROM properties p JOIN users u ON p.owner_id = u.user_id WHERE p.property_id = %s", (property_id,))
        prop = cursor.fetchone()
        if not prop: return "Proprietatea nu există", 404

        # Gasim zilele complet blocate pentru a le dezactiva in calendar
        cursor.execute("SELECT COUNT(idrooms) as total_rooms FROM rooms WHERE property_id = %s AND available = TRUE", (property_id,))
        total_available_rooms = cursor.fetchone()['total_rooms']
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

        # Preluam informatiile generale despre tipurile de camere (afisate default)
        cursor.execute("SELECT name, capacity, price, COUNT(*) as count FROM rooms WHERE property_id = %s GROUP BY name, capacity, price ORDER BY capacity DESC", (property_id,))
        room_groups_info = cursor.fetchall()

        # Pas 2: Daca avem tot ce ne trebuie, cautam automat recomandarile
        start_date, end_date = None, None
        if start_str and end_str:
            try:
                start_date = datetime.strptime(start_str.strip(), '%Y-%m-%d').date()
                end_date = datetime.strptime(end_str.strip(), '%Y-%m-%d').date()
            except (ValueError, IndexError): pass

        if requested_adults and requested_rooms and start_date and end_date:
            params = [property_id, start_date, end_date]
            room_query = "SELECT name, capacity, price, COUNT(*) as count, GROUP_CONCAT(idrooms) as room_ids FROM rooms WHERE property_id = %s AND available = TRUE AND idrooms NOT IN (SELECT room_id FROM reservations WHERE status = 'confirmed' AND NOT (end_date <= %s OR start_date >= %s)) GROUP BY name, capacity, price"
            cursor.execute(room_query, tuple(params))
            available_room_groups = cursor.fetchall()
            recommendations = get_recommendations(available_room_groups, requested_adults, requested_rooms)

            # Afisam un mesaj doar daca utilizatorul a apasat activ butonul (POST) si nu s-a gasit nimic
            if not recommendations and request.method == 'POST':
                flash("Nu s-a găsit nicio combinație pentru cerințele tale în perioada selectată.", "error")

    except MySQLError as e:
        print(f"Eroare la view_property: {e}")
        flash("A apărut o eroare la încărcarea paginii.", "error")
        return redirect('/')
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    return render_template("view_property.html", prop=prop, room_groups_info=room_groups_info, logged_in='user_id' in session,
                           recommendations=recommendations, requested_adults=requested_adults, requested_rooms=requested_rooms, period=period, locked_days=locked_days)


@app.route('/reserve/<int:room_id>', methods=['GET', 'POST'])
def reserve(room_id):
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.path))

    message, room, zile_indisponibile = None, None, set()
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        cursor.execute("SELECT r.*, p.name AS property_name FROM rooms r JOIN properties p ON r.property_id = p.property_id WHERE r.idrooms = %s", (room_id,))
        room = cursor.fetchone()
        if not room: return "Camera nu există", 404

        cursor.execute("SELECT start_date, end_date FROM reservations WHERE room_id = %s AND status = 'confirmed'", (room_id,))
        for r in cursor.fetchall():
            current = r['start_date']
            while current <= r['end_date']:
                zile_indisponibile.add(current.strftime('%Y-%m-%d'))
                current += timedelta(days=1)
    except MySQLError as e:
        message = f"Eroare la încărcarea datelor: {e}"
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    if request.method == 'POST':
        interval = request.form.get('date_range')
        try:
            if not interval or " to " not in interval: raise ValueError("Interval incomplet")
            start_date_str, end_date_str = interval.strip().split(" to ")
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if start_date >= end_date:
                message = "Data de final trebuie să fie după data de început."
            else:
                return redirect(url_for('finalize_reservation', room_id=room_id, start=start_date.isoformat(), end=end_date.isoformat()))
        except Exception:
            message = "Formatul perioadei este invalid. Asigură-te că selectezi un interval complet."

    return render_template("reserve.html", room=room, disabled_dates=list(zile_indisponibile), message=message, logged_in='user_id' in session)

@app.route('/booking/confirm', methods=['GET', 'POST'])
def booking_confirmation():
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.url))

    room_ids_str = request.args.get('ids')
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if not all([room_ids_str, start_str, end_str]):
        return "Date de rezervare incomplete.", 400

    room_id_list = room_ids_str.split(',')

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        nights = (end_date - start_date).days
        if nights <= 0: return "Perioadă invalidă.", 400
    except ValueError:
        return "Format de dată invalid.", 400

    package_rooms, total_price = [], 0
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        format_strings = ','.join(['%s'] * len(room_id_list))
        cursor.execute(f"SELECT r.*, p.name as property_name, p.address, p.city, p.country FROM rooms r JOIN properties p ON r.property_id = p.property_id WHERE r.idrooms IN ({format_strings})", tuple(room_id_list))
        package_rooms = cursor.fetchall()
        if len(package_rooms) != len(room_id_list):
            return "Una sau mai multe camere din pachet nu au fost găsite.", 404
        total_price = sum(room['price'] for room in package_rooms) * nights
    except MySQLError as e:
        print(f"Eroare la booking_confirmation (GET): {e}")
        flash("A apărut o eroare la încărcarea pachetului.", "error")
        return redirect(url_for('home'))
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    if request.method == 'POST':
        cnx_post, cursor_post = None, None
        try:
            cnx_post = db_pool.get_connection()
            cursor_post = cnx_post.cursor()
            cnx_post.start_transaction()

            first_reservation_id = None
            for room in package_rooms:
                cursor_post.execute("INSERT INTO reservations (user_id, room_id, start_date, end_date, status) VALUES (%s, %s, %s, %s, 'confirmed')",
                                    (session['user_id'], room['idrooms'], start_date, end_date))
                if not first_reservation_id:
                    first_reservation_id = cursor_post.lastrowid

            if first_reservation_id:
                cursor_post.execute("INSERT INTO reservation_details (reservation_id, full_name, phone, email, total_price) VALUES (%s, %s, %s, %s, %s)",
                                    (first_reservation_id, request.form['full_name'], request.form['phone'], request.form['email'], total_price))

            cnx_post.commit()
            session['last_booking_id'] = first_reservation_id
            return redirect(url_for('booking_success'))
        except MySQLError as e:
            if cnx_post: cnx_post.rollback()
            flash(f"A apărut o eroare la finalizarea rezervării: {e}", "error")
        finally:
            if cursor_post: cursor_post.close()
            if cnx_post: cnx_post.close()

    return render_template("booking_confirmation.html", package_rooms=package_rooms, start=start_str, end=end_str, total_price=total_price, nights=nights, logged_in='user_id' in session)

@app.route('/booking/success')
def booking_success():
    if 'user_id' not in session or 'last_booking_id' not in session:
        return redirect(url_for('home'))

    last_booking_id = session.pop('last_booking_id', None)
    if not last_booking_id:
        return redirect(url_for('my_reservations'))

    rezervare = None
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        cursor.execute("""
            SELECT res.*, r.name AS room_name, r.price AS room_price, p.name AS property_name,
                   p.address, p.city, p.country, DATEDIFF(res.end_date, res.start_date) AS nights,
                   det.full_name, det.phone, det.email, det.total_price
            FROM reservations res
            JOIN rooms r ON res.room_id = r.idrooms
            JOIN properties p ON r.property_id = p.property_id
            LEFT JOIN reservation_details det ON det.reservation_id = res.reservation_id
            WHERE res.reservation_id = %s
        """, (last_booking_id,))
        rezervare = cursor.fetchone()
    except MySQLError as e:
        print(f"Eroare la booking_success: {e}")
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    if not rezervare:
        flash("Nu am putut regăsi detaliile ultimei rezervări.", "error")
        return redirect(url_for('my_reservations'))

    return render_template("reservation_success.html", rezervare=rezervare, logged_in='user_id' in session)

@app.route('/my-reservations')
def my_reservations():
    if 'user_id' not in session: return redirect(url_for('login', next=request.url))
    reservations = []
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        # Am adaugat un LEFT JOIN catre reservation_details pentru a prelua noile date
        cursor.execute("""
            SELECT r.*, ro.name AS room_name, pr.name AS property_name,
                   det.full_name, det.phone, det.email, det.total_price
            FROM reservations r
            JOIN rooms ro ON r.room_id = ro.idrooms
            JOIN properties pr ON ro.property_id = pr.property_id
            LEFT JOIN reservation_details det ON det.reservation_id = r.reservation_id
            WHERE r.user_id = %s ORDER BY r.reservation_id DESC
        """, (session['user_id'],))
        reservations = cursor.fetchall()
    except MySQLError as e: print(f"Eroare la my_reservations: {e}")
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()
    return render_template('my_reservations.html', reservations=reservations, logged_in='user_id' in session)

@app.route('/my-properties')
def my_properties():
    if 'user_id' not in session: return redirect('/login')
    properties = []
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        cursor.execute("SELECT * FROM properties WHERE owner_id = %s", (session['user_id'],))
        properties = cursor.fetchall()
    except MySQLError as e:
        print(f"Eroare la proprietatile mele: {e}")
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()
    return render_template('my_properties.html', properties=properties, logged_in='user_id' in session, username=session.get('username'))


@app.route('/cancel_reservation/<int:reservation_id>')
def cancel_reservation(reservation_id):
    if 'user_id' not in session:
        return redirect(url_for('login', next=request.url))

    redirect_to_prop_id = request.args.get('redirect_to_prop_id', type=int) # Capture the redirect ID

    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        # Check if the reservation belongs to the current user OR to a property owned by the current user
        cursor.execute("""
            SELECT r.user_id, r.status, rm.property_id FROM reservations r
            JOIN rooms rm ON r.room_id = rm.idrooms
            WHERE r.reservation_id = %s
        """, (reservation_id,))
        reservation_info = cursor.fetchone()

        if not reservation_info:
            flash("Rezervarea nu există.", "error")
        elif reservation_info['user_id'] == session['user_id']:
            # User canceling their own reservation
            if reservation_info['status'] == 'cancelled':
                flash("Rezervarea este deja anulată.", "info")
            else:
                cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE reservation_id = %s", (reservation_id,))
                cnx.commit()
                flash("Rezervarea a fost anulată cu succes!", "success")
        else:
            # Check if current user owns the property associated with this reservation
            cursor.execute("SELECT owner_id FROM properties WHERE property_id = %s", (reservation_info['property_id'],))
            property_owner = cursor.fetchone()

            if property_owner and property_owner['owner_id'] == session['user_id']:
                if reservation_info['status'] == 'cancelled':
                    flash("Rezervarea este deja anulată.", "info")
                else:
                    cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE reservation_id = %s", (reservation_id,))
                    cnx.commit()
                    flash("Rezervarea a fost anulată cu succes de către proprietar!", "success")
            else:
                flash("Operațiune nepermisă. Nu dețineți această rezervare sau proprietatea asociată.", "error")

    except MySQLError as e:
        if cnx: cnx.rollback()
        flash(f"A apărut o eroare la anulare: {e}", "error")
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    # Redirect based on where the cancellation request originated
    if redirect_to_prop_id:
        return redirect(url_for('manage_property_reservations', property_id=redirect_to_prop_id))
    else:
        return redirect(url_for('my_reservations'))


# NEW ROUTE: Delete Property
@app.route('/delete_property/<int:property_id>')
def delete_property(property_id):
    if 'user_id' not in session:
        flash("Trebuie să fii autentificat pentru a șterge o proprietate.", "error")
        return redirect(url_for('login', next=request.url))

    cnx, cursor = None, None
    try: # Outer try block for database operations
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        # 1. Verify ownership
        cursor.execute("SELECT owner_id FROM properties WHERE property_id = %s", (property_id,))
        prop = cursor.fetchone()
        if not prop or prop['owner_id'] != session['user_id']:
            flash("Acces interzis sau proprietatea nu există.", "error")
            return redirect(url_for('my_properties'))

        # 2. Check for active/future confirmed reservations
        cursor.execute("""
            SELECT COUNT(*) AS res_count FROM reservations res
            JOIN rooms r ON res.room_id = r.idrooms
            WHERE r.property_id = %s AND res.status = 'confirmed' AND res.end_date >= CURDATE()
        """, (property_id,))

        if cursor.fetchone()['res_count'] > 0:
            flash("Nu puteți șterge o proprietate cu rezervări active sau viitoare. Anulați mai întâi rezervările confirmate pentru camerele acestei proprietăți.", "error")
            return redirect(url_for('my_properties'))

        # Delete reservation details associated with rooms of this property (if any)
        cursor.execute("""
            SELECT res.reservation_id FROM reservations res
            JOIN rooms r ON res.room_id = r.idrooms
            WHERE r.property_id = %s
        """, (property_id,))
        reservation_ids_to_delete = [row['reservation_id'] for row in cursor.fetchall()]

        if reservation_ids_to_delete:
            format_strings = ','.join(['%s'] * len(reservation_ids_to_delete))
            # Delete from reservation_details first to avoid foreign key constraints if they exist
            cursor.execute(f"DELETE FROM reservation_details WHERE reservation_id IN ({format_strings})", tuple(reservation_ids_to_delete))
            # Then delete from reservations table
            cursor.execute(f"DELETE FROM reservations WHERE reservation_id IN ({format_strings})", tuple(reservation_ids_to_delete))


        # Delete rooms associated with the property
        cursor.execute("DELETE FROM rooms WHERE property_id = %s", (property_id,))

        # Delete the property itself
        cursor.execute("DELETE FROM properties WHERE property_id = %s", (property_id,))

        cnx.commit()
        flash("Proprietatea a fost ștearsă cu succes!", "success")

    except MySQLError as e: # Catch any MySQLError during the operations
        if cnx: # Ensure cnx is not None before trying to rollback
            cnx.rollback()
        flash(f"A apărut o eroare la ștergerea proprietății: {e}", "error")
    finally: # Ensure cursor and connection are closed regardless of success or failure
        if cursor:
            cursor.close()
        if cnx:
            cnx.close()

    return render_template('my_properties.html', logged_in='user_id' in session, username=session.get('username'))

# NEW ROUTE: Manage Property Reservations
@app.route('/manage_property_reservations/<int:property_id>')
def manage_property_reservations(property_id):
    if 'user_id' not in session:
        flash("Trebuie să fii autentificat pentru a gestiona proprietăți.", "error")
        return redirect(url_for('login', next=request.url))

    prop = None
    reservations = []
    cnx, cursor = None, None
    try:
        cnx = db_pool.get_connection()
        cursor = cnx.cursor(dictionary=True)

        # Fetch property details and verify ownership
        cursor.execute("SELECT * FROM properties WHERE property_id = %s AND owner_id = %s", (property_id, session['user_id']))
        prop = cursor.fetchone()
        if not prop:
            flash("Acces interzis sau proprietatea nu există.", "error")
            return redirect(url_for('my_properties'))

        # Fetch reservations for this property, including user details and future/active bookings
        cursor.execute("""
            SELECT
                res.reservation_id, res.start_date, res.end_date, res.status,
                r.idrooms AS room_id, r.name AS room_name,
                det.full_name, det.email, det.phone, det.total_price
            FROM reservations res
            JOIN rooms r ON res.room_id = r.idrooms
            LEFT JOIN reservation_details det ON res.reservation_id = det.reservation_id
            WHERE r.property_id = %s AND res.end_date >= CURDATE()
            ORDER BY res.start_date ASC
        """, (property_id,))
        reservations = cursor.fetchall()

    except MySQLError as e:
        print(f"Eroare la manage_property_reservations: {e}")
        flash(f"A apărut o eroare la încărcarea rezervărilor: {e}", "error")
        return redirect(url_for('my_properties'))
    finally:
        if cursor: cursor.close()
        if cnx: cnx.close()

    return render_template('manage_property_reservations.html', prop=prop, reservations=reservations, logged_in='user_id' in session)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)