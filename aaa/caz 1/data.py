import pymysql
import bcrypt
import random
from tqdm import tqdm


DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '', 
    'cursorclass': pymysql.cursors.DictCursor
}
DB_NAME = 'rezervari'


NUM_USERS = 100
NUM_PROPERTIES = 200
BCRYPT_HASH = bcrypt.hashpw(b'parola123', bcrypt.gensalt())
CITIES = ['Cluj-Napoca', 'Craiova', 'Sibiu', 'Galati', 'Bucuresti', 'Brasov', 'Oradea', 'Iasi', 'Timisoara', 'Constanta']
CREATED_TIMESTAMP = '2025-08-14 14:49:17'
ROOM_TYPES = [
    {'name': 'Cameră Single', 'capacity': 1, 'price': 150.00},
    {'name': 'Cameră Dublă Standard', 'capacity': 2, 'price': 250.00},
    {'name': 'Cameră Twin', 'capacity': 2, 'price': 260.00},
    {'name': 'Cameră Triplă', 'capacity': 3, 'price': 320.00},
    {'name': 'Apartament', 'capacity': 4, 'price': 450.00},
    {'name': 'Suită Prezidențială', 'capacity': 4, 'price': 650.00}
]

def create_schema(cursor):
    """Creează toate tabelele necesare."""
    print("-> Crearea tabelelor...")
    
    tables_sql = [
        "CREATE TABLE `users` (`user_id` bigint NOT NULL AUTO_INCREMENT, `username` varchar(100) NOT NULL, `email` varchar(100) NOT NULL, `password` varchar(255) NOT NULL, `is_admin` tinyint(1) NOT NULL DEFAULT '0', `created_at` datetime DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (`user_id`), UNIQUE KEY `username` (`username`), UNIQUE KEY `email` (`email`)) ENGINE=InnoDB;",
        "CREATE TABLE `properties` (`property_id` bigint NOT NULL AUTO_INCREMENT, `owner_id` bigint NOT NULL, `name` varchar(150) NOT NULL, `description` varchar(500) DEFAULT NULL, `address` varchar(255) DEFAULT NULL, `city` varchar(100) DEFAULT NULL, `country` varchar(100) DEFAULT NULL, `created_at` datetime DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (`property_id`), KEY `fk_user_id` (`owner_id`), CONSTRAINT `fk_user_id` FOREIGN KEY (`owner_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE) ENGINE=InnoDB;",
        "CREATE TABLE `rooms` (`idrooms` bigint NOT NULL AUTO_INCREMENT, `property_id` bigint NOT NULL, `name` varchar(100) NOT NULL, `description` varchar(500) DEFAULT NULL, `capacity` int NOT NULL, `price` decimal(10,2) NOT NULL, `available` tinyint(1) DEFAULT '1', PRIMARY KEY (`idrooms`), KEY `fk_property_id` (`property_id`), CONSTRAINT `fk_property_id` FOREIGN KEY (`property_id`) REFERENCES `properties` (`property_id`) ON DELETE CASCADE ON UPDATE CASCADE) ENGINE=InnoDB;",
        "CREATE TABLE `reservations` (`reservation_id` bigint NOT NULL AUTO_INCREMENT, `user_id` bigint NOT NULL, `room_id` bigint NOT NULL, `start_date` date NOT NULL, `end_date` date NOT NULL, `status` enum('pending','confirmed','cancelled') DEFAULT 'pending', `created_at` datetime DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (`reservation_id`), KEY `fk_user_id_res` (`user_id`), KEY `fk_room_id` (`room_id`), CONSTRAINT `fk_room_id` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`idrooms`) ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT `fk_user_id_res` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE) ENGINE=InnoDB;",
        "CREATE TABLE `reservation_details` (`detail_id` int NOT NULL AUTO_INCREMENT, `reservation_id` bigint NOT NULL, `full_name` varchar(100) NOT NULL, `phone` varchar(20) DEFAULT NULL, `email` varchar(100) DEFAULT NULL, `total_price` decimal(10,2) NOT NULL, PRIMARY KEY (`detail_id`)) ENGINE=InnoDB;"
    ]
    
    for table_sql in tables_sql:
        cursor.execute(table_sql)
    print("-> Tabele create cu succes.")

def insert_data(cursor, cnx):
    """Generează și inserează toate datele de test."""
    
    # --- Inserare Utilizatori ---
    print(f"-> Generare și inserare a {NUM_USERS} utilizatori...")
    user_data = []
    for i in range(1, NUM_USERS + 1):
        user_data.append((f'test{i}', f'test{i}@example.com', BCRYPT_HASH))
    
    user_query = "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)"
    cursor.executemany(user_query, user_data)
    cnx.commit()
    print("-> Utilizatori inserați cu succes.")

    # --- Inserare Proprietăți ---
    print(f"-> Generare și inserare a {NUM_PROPERTIES} proprietăți...")
    property_data = []
    for i in range(1, NUM_PROPERTIES + 1):
        owner_id = random.randint(1, NUM_USERS)
        city = random.choice(CITIES)
        property_data.append((owner_id, f'Hotel Test {i}', f'Strada Test {i}', city, 'Romania'))
    
    prop_query = "INSERT INTO properties (owner_id, name, address, city, country) VALUES (%s, %s, %s, %s, %s)"
    cursor.executemany(prop_query, property_data)
    cnx.commit()
    print("-> Proprietăți inserate cu succes.")

    # --- Inserare Camere ---
    print("-> Generare și inserare camere pentru fiecare proprietate...")
    room_data = []
    for prop_id in tqdm(range(1, NUM_PROPERTIES + 1), desc="Adăugare Camere"):
        num_rooms_for_property = random.randint(2, 10) # Fiecare proprietate va avea între 2 și 10 camere
        for _ in range(num_rooms_for_property):
            room_type = random.choice(ROOM_TYPES)
            price = round(room_type['price'] * random.uniform(0.9, 1.2), 2) # Preț cu o mică variație
            room_data.append((prop_id, room_type['name'], room_type['capacity'], price, 1))

    room_query = "INSERT INTO rooms (property_id, name, capacity, price, available) VALUES (%s, %s, %s, %s, %s)"
    for i in tqdm(range(0, len(room_data), 1000), desc="Inserare Camere în DB"):
        cursor.executemany(room_query, room_data[i:i+1000])
        cnx.commit()
    print("-> Camere inserate cu succes.")

def main():
    cnx = None
    try:
        print("Conectare la serverul MySQL...")
        cnx = pymysql.connect(**DB_CONFIG)
        cursor = cnx.cursor()
        print("Conectare reușită.")

        print(f"Ștergere bază de date '{DB_NAME}' (dacă există)...")
        cursor.execute(f"DROP DATABASE IF EXISTS `{DB_NAME}`")
        print(f"Creare bază de date nouă '{DB_NAME}'...")
        cursor.execute(f"CREATE DATABASE `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        cursor.execute(f"USE `{DB_NAME}`")
        print("Baza de date a fost regenerată.")
        
        create_schema(cursor)
        insert_data(cursor, cnx)

        print("SUCCES!")
    

    except pymysql.MySQLError as e:
        print(f"\nEROARE MYSQL: {e}")
    finally:
        if cnx:
            cnx.close()
            print("Conexiune închisă.")

if __name__ == '__main__':
    main()