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
        
        with self.client.post("/login", data={"username": self.username, "password": self.password}, name="/login") as response:
            self.get_static_files(response)

    def get_static_files(self, response):
        """Extrage și încarcă fișierele statice locale dintr-un răspuns HTML."""
        if response.text and isinstance(response.text, str):
            for url in re.findall(r'["\'](/static/.*?\.?(?:css|js|png|ico))["\']', response.text):
                self.client.get(url, name="/static/[...]")

    @task(5)
    def browse_and_search(self):
        with self.client.get("/", name="/home") as response:
            self.get_static_files(response)

        with self.client.get("/my-reservations", name="/my-reservations") as response:
            self.get_static_files(response)

        start_date = datetime.now().date() + timedelta(days=random.randint(90, 150))
        end_date = start_date + timedelta(days=random.randint(2, 7))
        search_data = {
            "period": f"{start_date.isoformat()} to {end_date.isoformat()}",
            "destination": "Brasov", 
            "adults": 2, 
            "rooms": 1
        }
        with self.client.post("/search_results", data=search_data, name="/search_results") as response:
            self.get_static_files(response)

    @task(1)
    def manage_properties(self):
        add_data = {
            "name": f"Hotel Stres Test {random.randint(1, 1000)}", "address": "Strada Testarii",
            "city": "Sibiu", "country": "Romania", 
            "room_type_name[]": ["Cameră de Test"],
            "room_count[]": ["1"], "capacity[]": ["2"], "price[]": ["500"], "available[]": ["1"]
        }
        with self.client.post("/add_property", data=add_data, name="/add_property") as response:
            self.get_static_files(response)

        with self.client.get("/my-properties", name="/my-properties") as response:
            self.get_static_files(response)
            if response.ok:
                edit_links = re.findall(r'href="/edit_property/(\d+)"', response.text)
                if edit_links:
                    prop_id = random.choice(edit_links)
                    edit_data = {
                        "name": f"Hotel Editat Sub Stres {random.randint(1, 1000)}", "address": "Strada Noua",
                        "city": "Cluj", "country": "Romania", 
                        "room_type_name[]": ["Camera Editata"],
                        "room_count[]": ["1"], "capacity[]": ["1"], "price[]": ["100"], "available[]": ["1"]
                    }
                    with self.client.post(f"/edit_property/{prop_id}", data=edit_data, name="/edit_property/[id]") as edit_response:
                        self.get_static_files(edit_response)

    @task(2)
    def full_booking_flow(self):
        start_date = datetime.now().date() + timedelta(days=random.randint(200, 300))
        end_date = start_date + timedelta(days=random.randint(2, 5))
        
        search_data = {
            "period": f"{start_date.isoformat()} to {end_date.isoformat()}",
            "destination": "Bucuresti", "adults": 1, "rooms": 1
        }
        with self.client.post("/search_results", data=search_data, name="/search_results") as search_response:
            self.get_static_files(search_response)
            if not search_response.ok: return

            property_links = re.findall(r'href="(/property/\d+\?.*?)"', search_response.text)
            if not property_links: return

            property_link = random.choice(property_links).replace("&amp;", "&")
            with self.client.get(property_link, name="/property/[id]") as prop_response:
                self.get_static_files(prop_response)
                if not prop_response.ok: return
                
                booking_links = re.findall(r'href="(/booking/confirm\?.*?)"', prop_response.text)
                if not booking_links: return

                booking_link = random.choice(booking_links).replace("&amp;", "&")
                booking_data = {"full_name": "Test User", "phone": "0712345678", "email": "test@test.com"}
                with self.client.post(booking_link, name="/booking/confirm [POST]", data=booking_data) as booking_response:
                    self.get_static_files(booking_response)

    @task(3)
    def profile_and_edit(self):
        with self.client.get("/profile", name="/profile") as response:
            self.get_static_files(response)
        
        new_pass = "parola_noua123" if random.random() < 0.5 else ""
        edit_data = {
            "username": self.username, "email": f"edited_{self.username}@test.com", "password": new_pass
        }
        with self.client.post("/edit_profile", data=edit_data, name="/edit_profile") as response:
            self.get_static_files(response)
            if new_pass and response.ok:
                self.password = new_pass

    @task(1)
    def test_logout(self):
        with self.client.get("/logout", name="/logout") as response:
            self.get_static_files(response)