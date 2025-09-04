import random
import re
import time
from datetime import datetime, timedelta
from locust import HttpUser, task, between

class FinalArchitectureUser(HttpUser):
    wait_time = between(0.5, 2.5)
    host = "http://192.168.50.1"
    
    # -----------------------------------------------------------------------------
    # Modificat: Incarca toti cei 500 de utilizatori pentru a face testul realist
    # -----------------------------------------------------------------------------
    EXISTING_USER_CREDENTIALS = {f"test{i}": "parola123" for i in range(1, 501)}
    
    def on_start(self):
        time.sleep(random.uniform(0, 5))
        self.username = random.choice(list(self.EXISTING_USER_CREDENTIALS.keys()))
        self.password = self.EXISTING_USER_CREDENTIALS[self.username]
        self.client.post("/login", data={"username": self.username, "password": self.password}, name="/login")

    @task(5)
    def browse_and_search(self):
        self.client.get("/", name="/home")
        self.client.get("/my-reservations", name="/my-reservations")
        start_date = datetime.now().date() + timedelta(days=random.randint(90, 150))
        end_date = start_date + timedelta(days=random.randint(2, 7))
        self.client.post("/search_results", data={"period": f"{start_date.isoformat()} to {end_date.isoformat()}", "destination": "Brasov", "adults": 2, "rooms": 1}, name="/search_results")

    @task(1)
    def manage_properties(self):
        # --- REFACTORIZAT ---
        # Am eliminat blocul "with...as..." pentru a evita eroarea
        self.client.post("/add_property", data={
            "name": f"Hotel Stres Test {random.randint(1, 1000)}", "address": "Strada Testarii",
            "city": "Sibiu", "country": "Romania", "room_type_name": ["Cameră de Test"],
            "room_count": ["1"], "capacity": ["2"], "price": ["500"], "available": ["1"]
        }, name="/add_property")

        response = self.client.get("/my-properties", name="/my-properties")
        if response.status_code == 200:
            edit_links = re.findall(r'href="/edit_property/(\d+)"', response.text)
            if edit_links:
                prop_id = random.choice(edit_links)
                self.client.post(f"/edit_property/{prop_id}", data={
                    "name": f"Hotel Editat Sub Stres {random.randint(1, 1000)}", "address": "Strada Noua",
                    "city": "Cluj", "country": "Romania", "room_type_name": ["Camera Editata"],
                    "room_count": ["1"], "capacity": ["1"], "price": ["100"], "available": ["1"]
                }, name="/edit_property/[id]")

    @task(2)
    def full_booking_flow(self):
        # --- REFACTORIZAT ---
        # Am eliminat toate blocurile "with...as..."
        start_date = datetime.now().date() + timedelta(days=random.randint(200, 300))
        end_date = start_date + timedelta(days=random.randint(2, 5))
        
        search_response = self.client.post("/search_results", data={"period": f"{start_date.isoformat()} to {end_date.isoformat()}", "destination": "Bucuresti", "adults": 1, "rooms": 1}, name="/search_results")
        if search_response.status_code != 200:
            return

        property_links = re.findall(r'href="(/property/\d+\?.*?)"', search_response.text)
        if not property_links: 
            return

        property_link = random.choice(property_links).replace("&amp;", "&")
        
        prop_response = self.client.get(property_link, name="/property/[id]")
        if prop_response.status_code != 200:
            return

        booking_links = re.findall(r'href="(/booking/confirm\?.*?)"', prop_response.text)
        if not booking_links: 
            return

        booking_link = random.choice(booking_links).replace("&amp;", "&")
        self.client.post(booking_link, name="/booking/confirm [POST]", data={"full_name": "Test User", "phone": "0712345678", "email": "test@test.com"})

    @task(3)
    def spam_static_files(self):
        static_files = [
            "/static/css/style_add_property.css", "/static/css/style_admin.css",
            "/static/css/style_booking_confirmation.css", "/static/css/style_edit_profile.css",
            "/static/css/style_edit_property.css", "/static/css/style_home.css",
            "/static/css/style_login.css", "/static/css/style_manage_property_reservations.css",
            "/static/css/style_my_properties.css", "/static/css/style_my_reservations.css",
            "/static/css/style_profile.css", "/static/css/style_register.css",
            "/static/css/style_reservation_success.css", "/static/css/style_reserve.css",
            "/static/css/style_search_results.css", "/static/css/style_view_property.css"
        ]
        for file_path in static_files:
            self.client.get(file_path, name="/static/css/*")
