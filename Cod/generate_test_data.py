import mysql.connector
from mysql.connector import Error, pooling
import bcrypt 
from faker import Faker 
import random
from datetime import datetime, timedelta

# --- Configurația bazei de date (ASIGURĂ-TE CĂ ACESTEA SUNT CORECTE PENTRU MYSQL MASTER!) ---
DB_CONFIG = {
    'host': '127.0.0.1', 
    'database': 'rezervari', 
    'user': 'root', 
    'password': '', 
    'port': 3306 
}

# --- Configurații pentru numărul de intrări ---
NUM_USERS = 150 
NUM_PROPERTIES_PER_USER = 2 
NUM_ROOMS_PER_PROPERTY = 3 
NUM_RESERVATIONS_PER_USER = 2 # Câte rezervări per utilizator (pentru a avea mai multe rezervări)

# --- Lista de orașe specifice pentru generarea proprietăților ---
CITIES_TO_GENERATE = ["Bucuresti", "Cluj-Napoca", "Timisoara", "Brasov"]

# --- Inițializare Faker pentru date random ---
fake = Faker('en_US')

# --- Pool de conexiuni pentru a gestiona conexiunile eficient ---
try:
    connection_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="mypool",
        pool_size=5, 
        **DB_CONFIG
    )
except Error as e:
    print(f"Eroare la crearea pool-ului de conexiuni: {e}")
    exit()

def get_db_connection():
    """Obține o conexiune din pool."""
    try:
        return connection_pool.get_connection()
    except Error as e:
        print(f"Eroare la obținerea conexiunii din pool: {e}")
        return None

def hash_password(password):
    """Hash-uiește parola folosind bcrypt."""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def generate_user_data():
    """Generează date random pentru un utilizator."""
    username = fake.user_name() + str(random.randint(100, 999))
    email = fake.email()
    password = "password123" 
    hashed_password = hash_password(password)
    is_admin = 0 
    return username, email, hashed_password, is_admin

def insert_user(username, email, hashed_password, is_admin):
    """Inserează un utilizator în baza de date și returnează user_id."""
    connection = get_db_connection()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        query = "INSERT INTO users (username, email, password, is_admin) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (username, email, hashed_password, is_admin))
        connection.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"Eroare la inserarea utilizatorului {username}: {e}")
        connection.rollback()
        return None
    finally:
        cursor.close()
        connection.close()

def generate_property_data(owner_id):
    """Generează date random pentru o proprietate."""
    name = fake.company() + " Hotel"
    description = fake.paragraph(nb_sentences=3)
    address = fake.street_address()
    
    city = random.choice(CITIES_TO_GENERATE) 
    
    country = "Romania" 
    return owner_id, name, description, address, city, country

def insert_property(owner_id, name, description, address, city, country):
    """Inserează o proprietate în baza de date și returnează property_id."""
    connection = get_db_connection()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        query = "INSERT INTO properties (owner_id, name, description, address, city, country) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(query, (owner_id, name, description, address, city, country))
        connection.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"Eroare la inserarea proprietății {name}: {e}")
        connection.rollback()
        return None
    finally:
        cursor.close()
        connection.close()

def generate_room_data(): 
    """Generează date random pentru o cameră."""
    name = random.choice(["Single Room", "Double Room", "Suite", "Family Room", "Deluxe King"])
    description = fake.paragraph(nb_sentences=2)
    capacity = random.randint(1, 4)
    price = round(random.uniform(50, 300), 2)
    available = random.choice([0, 1]) 
    return name, description, capacity, price, available 

def insert_room(property_id, name, description, capacity, price, available):
    """Inserează o cameră în baza de date și returnează idrooms."""
    connection = get_db_connection()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        query = "INSERT INTO rooms (property_id, name, description, capacity, price, available) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(query, (property_id, name, description, capacity, price, available))
        connection.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"Eroare la inserarea camerei {name} pentru prop {property_id}: {e}")
        connection.rollback()
        return None
    finally:
        cursor.close()
        connection.close()

# --- Funcții pentru Rezervări (adaptate schemei SIMPLE `reservations` și adăugând `reservation_details`) ---

def generate_reservation_main_data(): 
    """Generează date random pentru coloanele principale ale tabelei `reservations`."""
    start_date_obj = fake.date_between(start_date='-6m', end_date='+6m')
    end_date_obj = start_date_obj + timedelta(days=random.randint(1, 10))
    status = random.choice(['confirmed', 'pending', 'cancelled'])
    return start_date_obj, end_date_obj, status

def insert_reservation_main(user_id, room_id, start_date, end_date, status): 
    """Inserează o rezervare în tabela `reservations` (fără detalii de contact)."""
    connection = get_db_connection()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        # Coloanele din tabela 'reservations' conform definiției tale actuale
        query = """
            INSERT INTO reservations (user_id, room_id, start_date, end_date, status)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (user_id, room_id, start_date, end_date, status))
        connection.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"Eroare la inserarea rezervării în tabela principală pentru user {user_id} și room {room_id}: {e}")
        connection.rollback()
        return None
    finally:
        cursor.close()
        connection.close()

def generate_reservation_details_data(reservation_id, room_price, start_date, end_date):
    """Generează date random pentru tabela `reservation_details`."""
    full_name = fake.name()
    phone = fake.phone_number()
    email = fake.email()
    
    num_days = (end_date - start_date).days if start_date and end_date else 1 # Asigură minim 1 zi
    total_price = round(num_days * room_price * random.uniform(0.9, 1.1), 2) # +-10% variatie

    return reservation_id, full_name, phone, email, total_price

def insert_reservation_details(reservation_id, full_name, phone, email, total_price):
    """Inserează detalii într-o rezervare în tabela `reservation_details`."""
    connection = get_db_connection()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        # Coloanele din tabela 'reservation_details' conform rezervari (2).sql
        query = """
            INSERT INTO reservation_details (reservation_id, full_name, phone, email, total_price)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (reservation_id, full_name, phone, email, total_price))
        connection.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"Eroare la inserarea detaliilor rezervării {reservation_id}: {e}")
        connection.rollback()
        return None
    finally:
        cursor.close()
        connection.close()

# --- Am eliminat complet funcțiile `generate_payment_data` și `insert_payment` ---


def main():
    print("Începe generarea datelor de test...")
    
    all_user_ids = []
    all_property_room_price_details = [] # Va stoca (property_id, room_id, room_price)

    # Generare utilizatori, proprietăți și camere asociate
    for i in range(NUM_USERS):
        username, email, hashed_password, is_admin = generate_user_data()
        user_id = insert_user(username, email, hashed_password, is_admin)
        if user_id:
            all_user_ids.append(user_id)
            print(f"Utilizator {username} (ID: {user_id}) inserat.")

            for j in range(NUM_PROPERTIES_PER_USER):
                owner_id, prop_name, prop_desc, prop_address, prop_city, prop_country = generate_property_data(user_id)
                property_id = insert_property(owner_id, prop_name, prop_desc, prop_address, prop_city, prop_country)
                if property_id:
                    print(f"  Proprietate {prop_name} (ID: {property_id}) pentru utilizatorul {user_id} inserată.")
                    for k in range(NUM_ROOMS_PER_PROPERTY):
                        room_name, room_desc, room_capacity, room_price, room_available = generate_room_data() 
                        
                        room_id = insert_room(property_id, room_name, room_desc, room_capacity, room_price, room_available)
                        if room_id:
                            all_property_room_price_details.append((property_id, room_id, room_price))
                            print(f"    Cameră {room_name} (ID: {room_id}) pentru proprietatea {property_id} inserată.")

    # Generare rezervări și detalii asociate (logica de plăți a fost eliminată)
    if all_user_ids and all_property_room_price_details:
        print("\nGenerare rezervări și detalii rezervări...")
        for _ in range(NUM_RESERVATIONS_PER_USER * len(all_user_ids)): 
            user_id = random.choice(all_user_ids)
            
            # Selectăm o proprietate și cameră random din lista celor generate
            property_id_chosen, room_id_chosen, room_price_chosen = random.choice(all_property_room_price_details)

            start_date_res, end_date_res, status_res = generate_reservation_main_data() 

            # Inserăm rezervarea în tabela `reservations` (cea simplificată)
            reservation_id = insert_reservation_main(user_id, room_id_chosen, start_date_res, end_date_res, status_res)
            
            if reservation_id:
                print(f"  Rezervare (ID: {reservation_id}) pentru user {user_id}, room {room_id_chosen} inserată.")
                
                # Inserăm detalii rezervare în tabela `reservation_details`
                detail_id = insert_reservation_details(
                    reservation_id, 
                    fake.name(), 
                    fake.phone_number(), 
                    fake.email(), 
                    (end_date_res - start_date_res).days * room_price_chosen # Calculează total_price aici din nou
                )
                if detail_id:
                    print(f"    Detalii rezervare (ID: {detail_id}) pentru rezervarea {reservation_id} inserate.")


    print("\nGenerare date finalizată.")
    print(f"Total utilizatori inserați: {len(all_user_ids)}")
    print(f"Total proprietăți inserate: {NUM_USERS * NUM_PROPERTIES_PER_USER}")
    print(f"Total camere inserate: {len(all_property_ids_with_room_details)}")
    print(f"Total rezervări generate (tentative): {NUM_RESERVATIONS_PER_USER * len(all_user_ids)}")


if __name__ == "__main__":
    # Setează o parolă de admin și un utilizator admin fix, pentru a te asigura că ai acces
    admin_username = "admin"
    admin_email = "admin@example.com"
    admin_password = "adminpassword123"
    hashed_admin_password = hash_password(admin_password)

    # Verifică dacă userul admin există deja
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(buffered=True)
        cursor.execute("SELECT user_id FROM users WHERE username = %s AND is_admin = 1", (admin_username,))
        existing_admin = cursor.fetchone()
        cursor.close()
        connection.close()
    else:
        existing_admin = None

    if not existing_admin:
        print(f"Inserare utilizator admin: {admin_username} cu parola: {admin_password}")
        insert_user(admin_username, admin_email, hashed_admin_password, 1) # is_admin = 1
    else:
        print(f"Utilizatorul admin '{admin_username}' există deja. Nu se inserează.")
    
    main()