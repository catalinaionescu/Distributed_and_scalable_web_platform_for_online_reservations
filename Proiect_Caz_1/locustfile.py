import random
import re
import time
from datetime import datetime, timedelta
from locust import HttpUser, task, between

class FinalArchitectureUser(HttpUser):
    wait_time = between(0.5, 2.5)
    host = "http://192.168.50.1"
    
    EXISTING_USER_CREDENTIALS = {f"test{i}": "parola123" for i in range(1, 501)}
    
    def on_start(self):
        """Se execută o singură dată la pornirea unui utilizator virtual."""
        time.sleep(random.uniform(0, 5))
        self.username = random.choice(list(self.EXISTING_USER_CREDENTIALS.keys()))
        self.password = self.EXISTING_USER_CREDENTIALS[self.username]
        
        with self.client.post("/login", data={"username": self.username, "password": self.password}, name="/login", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                self.get_static_files(response)
            else:
                response.failure(f"Login failed with status {response.status_code}")

    def get_static_files(self, response):
        # Extrage și cere fișierele statice dintr-un răspuns HTML
        if response.text:
            static_links = re.findall(r'href="/(static/.*?\.(?:css|js|png|ico))"|src="/(static/.*?\.(?:css|js|png|ico))"', response.text)
            for link_tuple in static_links:
                file_path = next((item for item in link_tuple if item), None)
                if file_path:
                    self.client.get(f"/{file_path}", name="/static/[...]")

    @task(5)
    def browse_and_search(self):
        # Task pentru navigare generală și căutare
        with self.client.get("/", name="/home", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                self.get_static_files(response)
            else:
                response.failure(f"GET / failed with status {response.status_code}")

        with self.client.get("/my-reservations", name="/my-reservations", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                self.get_static_files(response)
            else:
                response.failure(f"GET /my-reservations failed with status {response.status_code}")

        start_date = datetime.now().date() + timedelta(days=random.randint(90, 150))
        end_date = start_date + timedelta(days=random.randint(2, 7))
        with self.client.post("/search_results", data={"period": f"{start_date.isoformat()} to {end_date.isoformat()}", "destination": "Brasov", "adults": 2, "rooms": 1}, name="/search_results", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                self.get_static_files(response)
            else:
                response.failure(f"POST /search_results failed with status {response.status_code}")

    @task(1)
    def manage_properties(self):
        # Task pentru adăugarea și editarea proprietăților
        with self.client.post("/add_property", data={
            "name": f"Hotel Stres Test {random.randint(1, 1000)}", "address": "Strada Testarii",
            "city": "Sibiu", "country": "Romania", "room_type_name": ["Cameră de Test"],
            "room_count": ["1"], "capacity": ["2"], "price": ["500"], "available": ["1"]
        }, name="/add_property", catch_response=True) as response:
            response.success()
            self.get_static_files(response)

        with self.client.get("/my-properties", name="/my-properties", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                self.get_static_files(response)
                edit_links = re.findall(r'href="/edit_property/(\d+)"', response.text)
                if edit_links:
                    prop_id = random.choice(edit_links)
                    with self.client.post(f"/edit_property/{prop_id}", data={
                        "name": f"Hotel Editat Sub Stres {random.randint(1, 1000)}", "address": "Strada Noua",
                        "city": "Cluj", "country": "Romania", "room_type_name": ["Camera Editata"],
                        "room_count": ["1"], "capacity": ["1"], "price": ["100"], "available": ["1"]
                    }, name="/edit_property/[id]", catch_response=True) as edit_response:
                        edit_response.success()
                        self.get_static_files(edit_response)
            else:
                response.failure(f"GET /my-properties failed with status {response.status_code}")

    @task(2)
    def full_booking_flow(self):
        # Task ce simulează un flux complet de rezervare
        start_date = datetime.now().date() + timedelta(days=random.randint(200, 300))
        end_date = start_date + timedelta(days=random.randint(2, 5))
        
        with self.client.post("/search_results", data={"period": f"{start_date.isoformat()} to {end_date.isoformat()}", "destination": "Bucuresti", "adults": 1, "rooms": 1}, name="/search_results", catch_response=True) as search_response:
            if search_response.status_code == 200:
                search_response.success()
                self.get_static_files(search_response)
                
                property_links = re.findall(r'href="(/property/\d+\?.*?)"', search_response.text)
                if not property_links: return

                property_link = random.choice(property_links).replace("&amp;", "&")
                
                with self.client.get(property_link, name="/property/[id]", catch_response=True) as prop_response:
                    if prop_response.status_code == 200:
                        prop_response.success()
                        self.get_static_files(prop_response)
                        
                        booking_links = re.findall(r'href="(/booking/confirm\?.*?)"', prop_response.text)
                        if not booking_links: return

                        booking_link = random.choice(booking_links).replace("&amp;", "&")
                        with self.client.post(booking_link, name="/booking/confirm [POST]", data={"full_name": "Test User", "phone": "0712345678", "email": "test@test.com"}, catch_response=True) as booking_response:
                            booking_response.success()
                            self.get_static_files(booking_response)
                    else:
                        prop_response.failure(f"GET /property/[id] failed with status {prop_response.status_code}")
            else:
                search_response.failure(f"POST /search_results in booking flow failed with status {search_response.status_code}")

    @task(3)
    def profile_and_edit(self):
        # Task pentru vizualizarea și editarea profilului
        with self.client.get("/profile", name="/profile", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                self.get_static_files(response)
            else:
                response.failure(f"GET /profile failed with status {response.status_code}")
        
        new_pass = "parola_noua123" if random.random() < 0.5 else ""
        with self.client.post("/edit_profile", data={
            "username": self.username, 
            "email": f"edited_{self.username}@test.com", 
            "password": new_pass
        }, name="/edit-profile", catch_response=True) as response:
            response.success()
            self.get_static_files(response)
            if new_pass:
                self.password = new_pass

    @task(1)
    def test_logout(self):
        # Task simplu pentru logout
        with self.client.get("/logout", name="/logout", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                self.get_static_files(response)
            else:
                response.failure(f"GET /logout failed with status {response.status_code}")