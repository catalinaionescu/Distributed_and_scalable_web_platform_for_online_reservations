from locust import HttpUser, task, between, SequentialTaskSet
import time
import random
import csv
import mysql.connector
from mysql.connector import Error

from datetime import datetime, timedelta
from faker import Faker # Import Faker here for usage in UserTasks if needed, though usually handled by generate_test_data.py

# --- Configurația bazei de date (pentru a prelua ID-uri la startul testului Locust) ---
# Aceasta trebuie să fie aceeași configurație ca în generate_test_data.py
DB_CONFIG = {
    'host': '127.0.0.1', 
    'database': 'rezervari', 
    'user': 'your_mysql_user', 
    'password': 'your_mysql_password', 
    'port': 3306 
}

# --- Date de test preîncărcate ---
TEST_USERS = []
TEST_PROPERTIES_AND_ROOMS = [] # Va stoca (property_id, room_id, room_price)

# Inițializare Faker pentru a putea genera date fake în task-uri dacă e nevoie
fake = Faker('en_US')

def load_initial_data():
    """Încarcă useri și proprietăți/camere din baza de date pentru task-uri."""
    global TEST_USERS, TEST_PROPERTIES_AND_ROOMS
    
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT username FROM users WHERE is_admin = 0 LIMIT 5000") 
        TEST_USERS = [[row[0], "password123"] for row in cursor.fetchall()]

        cursor.execute("SELECT p.property_id, r.idrooms, r.price FROM properties p JOIN rooms r ON p.property_id = r.property_id LIMIT 5000")
        TEST_PROPERTIES_AND_ROOMS = [(row[0], row[1], float(row[2])) for row in cursor.fetchall()]

        print(f"Locust: Loaded {len(TEST_USERS)} test users and {len(TEST_PROPERTIES_AND_ROOMS)} properties/rooms from DB.")

    except Error as e:
        print(f"Locust ERROR: Could not load initial data from DB: {e}")
        print("Locust: Running with fallback data (might cause errors if not configured).")
        TEST_USERS.append(["default_user", "password123"]) 
        TEST_PROPERTIES_AND_ROOMS.append((1, 1, 100.00))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

load_initial_data()


class UserTasks(SequentialTaskSet):
    """
    Acest TaskSet definește un flux secvențial de acțiuni ale utilizatorului.
    """

    def on_start(self):
        """
        Metoda on_start este apelată o singură dată pentru fiecare utilizator virtual.
        Fiecare utilizator virtual va încerca să se autentifice.
        """
        self.is_logged_in = False
        self.username = "default_user_locust" 
        self.password = "password123" 

        if TEST_USERS:
            try:
                self.username, self.password = TEST_USERS.pop(0) 
            except IndexError:
                print("WARNING: Ran out of unique test users from TEST_USERS list. Reusing existing users or will fail to log in.")
                self.username, self.password = random.choice(TEST_USERS) if TEST_USERS else ("fallback_user", "password123")


            print(f"Starting user: {self.username} (Spawned user count: {self.user.environment.runner.user_count})")
            self.login_user()
        else:
            print("No test users available. Skipping login for this user.")
            self.user.environment.events.request.fire(request_type="init", name="no_test_users_available",
                                                    response_time=0, response_length=0, exception=Exception("No test users loaded for login"))


    def login_user(self):
        """Simulează autentificarea unui utilizator."""
        if not self.is_logged_in:
            login_response = self.user.client.post("/login", {
                "username": self.username,
                "password": self.password
            }, name="/login [TaskSet Init]")

            if login_response.status_code in [200, 302]:
                self.is_logged_in = True
                print(f"User {self.username} logged in successfully (Status: {login_response.status_code}).")
            else:
                print(f"User {self.username} failed to log in. Status: {login_response.status_code}, Response: {login_response.text}")
                self.user.environment.events.request.fire(request_type="login_flow", name="login_failed",
                                                            response_time=0, response_length=0, exception=Exception(f"Login failed for {self.username}"))
                self.is_logged_in = False 

    @task(10)
    def view_homepage(self):
        """Simulează vizualizarea paginii principale."""
        if not self.is_logged_in: 
            self.login_user()
            if not self.is_logged_in: return 

        self.user.client.get("/", name="/ [Homepage]")
        print(f"User {self.user.environment.runner.user_count} viewed homepage.")

    @task(5)
    def search_properties(self):
        """Simulează căutarea proprietăților cu parametri."""
        if not self.is_logged_in:
            self.login_user()
            if not self.is_logged_in: return

        destination = random.choice(["Bucuresti", "Cluj-Napoca", "Timisoara", "Brasov"])
        start_date = "2025-07-01" 
        end_date = "2025-07-07"
        adults = random.randint(1, 4)
        rooms_needed = random.randint(1, 2)

        self.user.client.get(f"/search_results?destination={destination}&start_date={start_date}&end_date={end_date}&adults={adults}&rooms_needed={rooms_needed}",
                            name="/search_results [GET]")
        print(f"User {self.user.environment.runner.user_count} searched for properties in {destination}.")

    @task(3)
    def view_property_details(self):
        """Simulează vizualizarea detaliilor unei proprietăți (folosind un ID din DB)."""
        if not self.is_logged_in:
            self.login_user()
            if not self.is_logged_in: return

        if not TEST_PROPERTIES_AND_ROOMS:
            print("No properties/rooms loaded, skipping view_property_details.")
            self.user.environment.events.request.fire(request_type="action", name="no_properties_for_view",
                                                        response_time=0, response_length=0, exception=Exception("No properties/rooms loaded"))
            return

        property_id_chosen, room_id_chosen, room_price_chosen = random.choice(TEST_PROPERTIES_AND_ROOMS)

        self.user.client.get(f"/property/{property_id_chosen}", name="/property/[id] [GET]")
        print(f"User {self.user.environment.runner.user_count} viewed property {property_id_chosen} details.")

    @task(2) 
    def make_reservation_flow(self):
        """Simulează un flux complet de rezervare (necesită login)."""
        if not self.is_logged_in:
            self.login_user()
            if not self.is_logged_in: return

        if not TEST_PROPERTIES_AND_ROOMS:
            print("No properties/rooms loaded, skipping reservation flow.")
            self.user.environment.events.request.fire(request_type="action", name="no_properties_for_booking",
                                                        response_time=0, response_length=0, exception=Exception("No properties/rooms loaded for booking"))
            return

        try:
            property_id_chosen, room_id_chosen, room_price_chosen = random.choice(TEST_PROPERTIES_AND_ROOMS)

            start_date_obj = datetime.now().date() + timedelta(days=random.randint(1, 30))
            end_date_obj = start_date_obj + timedelta(days=random.randint(1, 5))
            adults_for_booking = random.randint(1, 2)
            rooms_needed_for_booking = random.randint(1,2) # Poate fi mai mult de 1 camera

            # --- Pasul 1: Vizitează pagina proprietății cu parametri de căutare (GET) ---
            self.user.client.get(f"/property/{property_id_chosen}?start_date={start_date_obj.strftime('%Y-%m-%d')}&end_date={end_date_obj.strftime('%Y-%m-%d')}&adults={adults_for_booking}&rooms_needed={rooms_needed_for_booking}",
                                name="/property/[id]?search_params [GET for booking]")
            
            # --- Pasul 2: Trimite cererea POST pentru a iniția rezervarea (spre /booking/confirm) ---
            # Asigură-te că toate aceste câmpuri sunt cele așteptate de backend-ul tău Flask!
            booking_confirm_data = {
                "property_id": str(property_id_chosen), 
                "room_id": str(room_id_chosen),
                "start_date": start_date_obj.strftime('%Y-%m-%d'),
                "end_date": end_date_obj.strftime('%Y-%m-%d'),
                "adults": str(adults_for_booking),
                "rooms_needed": str(rooms_needed_for_booking), 
                "reserve_room": "Rezerva"
            }
            booking_confirm_response = self.user.client.post("/booking/confirm", booking_confirm_data, name="/booking/confirm [POST]")

            if booking_confirm_response.status_code in [200, 302]:
                # --- Pasul 3: Trimite cererea POST pentru a finaliza rezervarea (spre /booking/success) ---
                # AICI SUNT DETALIILE DE CONTACT ȘI PREȚUL TOTAL PENTRU `reservation_details`
                
                num_days_res = (end_date_obj - start_date_obj).days if start_date_obj and end_date_obj else 1
                calculated_total_price = round(num_days_res * room_price_chosen * adults_for_booking, 2) # Folosim room_price_chosen din DB
                
                final_booking_data = {
                    "full_name": fake.name(), # Folosim fake.name() etc. pentru detalii contact
                    "phone": fake.phone_number(),
                    "email": fake.email(),
                    "total_price": str(calculated_total_price), 
                    "confirm_booking": "Confirma Rezervarea" 
                }
                final_reserve_response = self.user.client.post("/booking/success", final_booking_data, name="/booking/success [POST]")

                if final_reserve_response.status_code in [200, 302]:
                    print(f"User {self.username} successfully made a reservation for property {property_id_chosen} room {room_id_chosen}.")
                else:
                    print(f"User {self.username} failed final reservation. Status: {final_reserve_response.status_code}, Response: {final_reserve_response.text}")
                    self.user.environment.events.request.fire(request_type="reservation_flow", name="make_reservation_flow_error_final",
                                                            response_time=0, response_length=0, exception=Exception(f"Final booking failed for {self.username}: {final_reserve_response.text}"))
            else:
                print(f"User {self.username} failed booking confirmation. Status: {booking_confirm_response.status_code}, Response: {booking_confirm_response.text}")
                self.user.environment.events.request.fire(request_type="reservation_flow", name="make_reservation_flow_error_confirm",
                                                            response_time=0, response_length=0, exception=Exception(f"Booking confirm failed for {self.username}: {booking_confirm_response.text}"))

        except Exception as e:
            print(f"An error occurred during make_reservation_flow for {self.username}: {e}")
            self.user.environment.events.request.fire(request_type="reservation_flow", name="make_reservation_flow_error_exception",
                                                response_time=0, response_length=0, exception=e)

    @task(1) 
    def view_dashboard(self):
        """Simulează vizualizarea paginii de profil (dashboard)."""
        if not self.is_logged_in:
            self.login_user()
            if not self.is_logged_in: return

        self.user.client.get("/profile", name="/profile [GET]")
        print(f"User {self.user.environment.runner.user_count} viewed dashboard.")

    @task(0) 
    def logout_user(self):
        """Simulează delogarea utilizatorului."""
        if self.is_logged_in:
            self.user.client.get("/logout", name="/logout [GET]")
            self.is_logged_in = False
            print(f"User {self.username} logged out.")


class WebsiteUser(HttpUser):
    """
    Clasa WebsiteUser definește comportamentul unui utilizator virtual
    care interacționează cu aplicația web.
    """
    wait_time = between(1, 5) 

    host = "http://localhost:8080" # Schimbă asta în funcție de caz (ex: http://localhost:5000 pentru Cazul 1)

    tasks = {UserTasks: 1}