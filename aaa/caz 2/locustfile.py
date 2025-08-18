import random
import re
from datetime import datetime, timedelta

# Importurile necesare din biblioteca locust.
from locust import HttpUser, task, between


class ApiUser(HttpUser):
    """
    Un singur tip de utilizator care testează fiecare endpoint individual.
    """
    # Timp de așteptare între task-uri, simulează comportamentul unui utilizator real
    wait_time = between(1, 3)
    
    # Adresa serverului care va fi testat
    host = "http://localhost:5000"
    
    # Definim credențialele utilizatorilor pre-existenți pentru login
    EXISTING_USER_CREDENTIALS = {f"test{i}": "parola123" for i in range(1, 51)}
    
    def on_start(self):
        """ Se autentifică la începutul sesiunii pentru fiecare utilizator simulat. """
        self.username = random.choice(list(self.EXISTING_USER_CREDENTIALS.keys()))
        self.password = self.EXISTING_USER_CREDENTIALS[self.username]
        self.client.post("/login", data={"username": self.username, "password": self.password}, name="/login")

    @task(1)
    def test_register(self):
        """Task: Testează ruta /register."""
        random_id = random.randint(10000, 99999)
        username = f"locust_user_{random_id}"
        email = f"locust_user_{random_id}@test.com"
        self.client.post("/register", data={"username": username, "email": email, "password": "password"}, name="/register")

    @task(10)
    def test_home_and_search(self):
        """Task: Testează paginile / și /search_results."""
        self.client.get("/", name="/")
        
        start_date = datetime.now().date() + timedelta(days=random.randint(90, 150))
        end_date = start_date + timedelta(days=random.randint(1, 5))
        
        self.client.post("/search_results", data={"period": f"{start_date.isoformat()} to {end_date.isoformat()}", "destination": "Bucuresti", "adults": 1, "rooms": 1}, name="/search_results")

    @task(5)
    def test_add_property(self):
        """Task: Testează ruta /add_property."""
        self.client.post("/add_property", data={
            "name": f"Hotel Nou {random.randint(1, 1000)}",
            "address": "Strada Noua",
            "city": "Bucuresti",
            "country": "Romania",
            "room_type_name": ["Camera Dubla"],
            "room_count": ["1"],
            "capacity": ["1"],
            "price": ["150"],
            "available": ["1"]
        }, name="/add_property")

    @task(5)
    def test_edit_property(self):
        """Task: Testează ruta /edit_property."""
        with self.client.get("/my-properties", name="/my-properties", catch_response=True) as response:
            property_ids = re.findall(r'prop-id-(\d+)', response.text)
            if property_ids:
                prop_id = random.choice(property_ids)
                self.client.post(f"/edit_property/{prop_id}", data={
                    "name": f"Hotel Editat {random.randint(1, 1000)}", 
                    "address": "Strada Editata", 
                    "city": "Cluj", 
                    "country": "Romania",
                    "room_type_name": ["Camera Tripla"], 
                    "room_count": ["2"], 
                    "capacity": ["2"], 
                    "price": ["250"], 
                    "available": ["1"]
                }, name="/edit_property/[id]")

    @task(2)
    def test_delete_property(self):
        """Task: Testează ruta /delete_property."""
        with self.client.get("/my-properties", name="/my-properties", catch_response=True) as response:
            property_ids = re.findall(r'prop-id-(\d+)', response.text)
            if property_ids:
                # Se alege un ID aleatoriu din lista de proprietăți găsite
                prop_id = random.choice(property_ids)
                self.client.get(f"/delete_property/{prop_id}", name="/delete_property/[id]")

    @task(8)
    def test_view_property_and_reservations_pages(self):
        """Task: Testează vizualizarea proprietăților și a rezervărilor."""
        with self.client.get("/my-properties", name="/my-properties", catch_response=True) as response:
            property_ids = re.findall(r'prop-id-(\d+)', response.text)
            if property_ids:
                prop_id = random.choice(property_ids)
                self.client.get(f"/manage_property_reservations/{prop_id}", name="/manage_property_reservations/[id]")

    @task(8)
    def test_profile_pages(self):
        """Task: Testează rutele de profil."""
        self.client.get("/profile", name="/profile")
        
        self.client.post("/edit-profile", data={"username": self.username, "email": f"edited_{self.username}@test.com", "current_password": self.password, "new_password": "", "confirm_new_password": ""}, name="/edit-profile")

    @task(8)
    def test_booking_and_cancellation(self):
        """Task: Testează rutele de booking, succes și anulare."""
        room_id = random.randint(1, 400)
        start_date = datetime.now().date() + timedelta(days=random.randint(200, 300))
        end_date = start_date + timedelta(days=random.randint(1, 5))
        start_str, end_str = start_date.isoformat(), end_date.isoformat()

        self.client.get(f"/booking/confirm?ids={room_id}&start={start_str}&end={end_str}", name="/booking/confirm")

        with self.client.post(
            "/booking/confirm", data={"room_ids": str(room_id), "start_date": start_str, "end_date": end_str, "full_name": "Test User", "phone": "0712345678", "email": "test@test.com"},
            name="/booking/confirm", catch_response=True, allow_redirects=False
        ) as conf_response:
            if conf_response.status_code == 302:
                conf_response.success()
                self.client.get("/booking/success", name="/booking/success")

        with self.client.get("/my-reservations", name="/my-reservations", catch_response=True) as res_response:
            if res_response.status_code == 200:
                res_response.success()
                reservation_ids = re.findall(r'href="/cancel_reservation/(\d+)"', res_response.text)
                if reservation_ids:
                    # Se alege un ID de rezervare aleatoriu pentru anulare
                    res_id = random.choice(reservation_ids)
                    self.client.get(f"/cancel_reservation/{res_id}", name="/cancel_reservation/[id]")
    
    @task(1)
    def test_logout(self):
        """Task: Testează ruta /logout."""
        self.client.get("/logout", name="/logout")