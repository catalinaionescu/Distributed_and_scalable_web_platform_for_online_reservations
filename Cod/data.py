import mysql.connector
import bcrypt
import random
from datetime import datetime, timedelta

# Configurația bazei de date - AICI TREBUIE SĂ MODIFICI CU DETALIILE TALE
DB_CONFIG = {
    'host': 'localhost',  # Asigură-te că este IP-ul corect pentru serverul tău Master DB
    'user': 'root',
    'password': '',  # Asigură-te că aceasta e parola corectă
    'database': 'rezervari',
}

# Liste de date de test conform cerințelor
CITIES = [
    "Bucuresti", "Cluj-Napoca", "Timisoara", "Brasov", "Sibiu",
    "Iasi", "Constanta", "Oradea", "Galati", "Craiova"
]

ROOM_TYPES = [
    "Cameră Dublă Standard", "Cameră Twin", "Apartament Deluxe",
    "Garsonieră", "Cameră Triplă", "Suită Prezidențială"
]

def generate_test_data():
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cursor = cnx.cursor()

        # 1. Generare utilizatori (număr exact)
        users_count = 50
        users_data = []
        password = "parola123".encode('utf-8')
        hashed_password = bcrypt.hashpw(password, bcrypt.gensalt())
        for i in range(1, users_count + 1):
            username = f"test{i}"
            email = f"test{i}@example.com"
            users_data.append((username, hashed_password, email))
        
        insert_user_query = "INSERT INTO users (username, password, email) VALUES (%s, %s, %s)"
        cursor.executemany(insert_user_query, users_data)
        cnx.commit()
        print(f"Am inserat cu succes {cursor.rowcount} utilizatori.")
        
        cursor.execute("SELECT user_id FROM users WHERE username LIKE 'test%'")
        user_ids = [row[0] for row in cursor.fetchall()]

        # 2. Generare proprietăți și camere (număr exact)
        properties_count = 100
        properties_per_user = properties_count // users_count
        room_types_per_property = 2
        rooms_per_type = 2 
        
        all_room_ids = []
        owner_id_index = 0

        for i in range(properties_count):
            owner_id = user_ids[owner_id_index]
            owner_id_index = (owner_id_index + 1) % users_count

            name = f"Hotel Test {i+1}"
            address = f"Strada Test {i+1}"
            city = random.choice(CITIES)
            country = "Romania"
            
            insert_prop_query = "INSERT INTO properties (name, address, city, country, owner_id) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(insert_prop_query, (name, address, city, country, owner_id))
            property_id = cursor.lastrowid
            
            room_types_for_prop = random.sample(ROOM_TYPES, k=room_types_per_property)
            for room_type_name in room_types_for_prop:
                capacity = random.randint(1, 4)
                price = random.randint(50, 500)
                for _ in range(rooms_per_type):
                    insert_room_query = "INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (%s, %s, %s, %s, TRUE)"
                    cursor.execute(insert_room_query, (property_id, room_type_name, capacity, price))
                    all_room_ids.append(cursor.lastrowid)

        cnx.commit()
        print(f"Am inserat cu succes {properties_count} proprietăți.")
        print(f"Am inserat un total de {len(all_room_ids)} camere.")

        # 3. Generare rezervări (număr exact)
        reservations_count = 250
        
        if not all_room_ids:
            print("Nu există camere disponibile pentru a crea rezervări.")
            return

        user_id_index = 0
        room_id_index = 0
        
        for i in range(reservations_count):
            user_id = user_ids[user_id_index]
            user_id_index = (user_id_index + 1) % users_count
            
            room_id = all_room_ids[room_id_index]
            room_id_index = (room_id_index + 1) % len(all_room_ids)

            start_date = datetime.now() + timedelta(days=random.randint(1, 60))
            end_date = start_date + timedelta(days=random.randint(1, 7))

            insert_res_query = "INSERT INTO reservations (user_id, room_id, start_date, end_date, status) VALUES (%s, %s, %s, %s, 'confirmed')"
            cursor.execute(insert_res_query, (user_id, room_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
            reservation_id = cursor.lastrowid
            
            total_price = random.randint(100, 1000)
            full_name = f"User {user_id}"
            phone = f"0712345{random.randint(10, 99)}"
            email = f"user{user_id}@test.com"
            insert_details_query = "INSERT INTO reservation_details (reservation_id, full_name, phone, email, total_price) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(insert_details_query, (reservation_id, full_name, phone, email, total_price))

        cnx.commit()
        print(f"Am inserat cu succes {reservations_count} rezervări.")
        
        print("\n--- Sumar ---")
        print(f"Utilizatori generați: {users_count}")
        print(f"Proprietăți generate: {properties_count}")
        print(f"Camere generate: {len(all_room_ids)}")
        print(f"Rezervări generate: {reservations_count}")

    except mysql.connector.Error as err:
        print(f"Eroare: {err}")
    finally:
        if 'cnx' in locals() and cnx.is_connected():
            cursor.close()
            cnx.close()

if __name__ == '__main__':
    generate_test_data()