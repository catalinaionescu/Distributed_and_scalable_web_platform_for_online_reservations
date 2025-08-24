import random
import re
import time
from datetime import datetime, timedelta
from locust import HttpUser, task, between

class TotalChaosUser(HttpUser):
    """
    Simulează un utilizator extrem de agresiv care bombardează serverul
    cu toate tipurile posibile de cereri pentru a stresa la maximum sistemul.
    """
    wait_time = between(0.5, 1.5) # Pauze foarte scurte pentru presiune maximă
    
    # !!! IMPORTANT: Schimbă host-ul în funcție de testul pe care îl rulezi !!!
    
    # --- PENTRU CAZUL 1 (Nginx + IIS + Master-Slave) ---
    host = "http://localhost:5000"
    
    # --- PENTRU CAZUL 2 (doar Flask, fără Nginx) ---
    # host = "http://localhost:5000"
    
    EXISTING_USER_CREDENTIALS = {f"test{i}": "parola123" for i in range(1, 51)}
    
    def on_start(self):
        """ Se loghează o singură dată la începutul sesiunii. """
        time.sleep(random.uniform(0, 5)) # Pauză mai mare la început pentru a gestiona login-urile
        self.username = random.choice(list(self.EXISTING_USER_CREDENTIALS.keys()))
        self.password = self.EXISTING_USER_CREDENTIALS[self.username]
        self.client.post("/login", data={"username": self.username, "password": self.password}, name="/login")

    @task
    def chaos_test(self):
        """Task principal care execută un amestec haotic de absolut toate acțiunile."""
        
        actions = [
            self.browse_and_search,
            self.manage_properties,
            self.full_booking_flow,
            self.spam_static_files,
            self.update_profile
        ]
        
        # Execută o acțiune la întâmplare la fiecare pas
        random.choice(actions)()

    def browse_and_search(self):
        """Accesează pagini de bază și face o căutare."""
        self.client.get("/", name="/")
        self.client.get("/my-reservations", name="/my-reservations")
        start_date = datetime.now().date() + timedelta(days=random.randint(90, 150))
        end_date = start_date + timedelta(days=random.randint(2, 7))
        self.client.post("/search_results", data={"period": f"{start_date.isoformat()} to {end_date.isoformat()}", "destination": "Brasov", "adults": 2, "rooms": 1}, name="/search_results")

    def manage_properties(self):
        """Adaugă, editează și șterge proprietăți."""
        # Adaugă o proprietate nouă
        self.client.post("/add_property", data={
            "name": f"Hotel Haos {random.randint(1, 1000)}", "address": "Strada Distrugerii",
            "city": "Sibiu", "country": "Romania", "room_type_name": ["Cameră Haos"],
            "room_count": ["1"], "capacity": ["2"], "price": ["999"], "available": ["1"]
        }, name="/add_property")

        # Găsește o proprietate existentă pentru a o edita/șterge
        with self.client.get("/my-properties", name="/my-properties", catch_response=True) as response:
            edit_links = re.findall(r'href="/edit_property/(\d+)"', response.text)
            if edit_links:
                prop_id = random.choice(edit_links)
                self.client.post(f"/edit_property/{prop_id}", data={
                    "name": f"Hotel Editat Haotic {random.randint(1, 1000)}", "address": "Strada Noua",
                    "city": "Cluj", "country": "Romania", "room_type_name": ["Camera Editata"],
                    "room_count": ["1"], "capacity": ["1"], "price": ["100"], "available": ["1"]
                }, name="/edit_property/[id]")

            delete_links = re.findall(r'href="/delete_property/(\d+)"', response.text)
            if delete_links:
                prop_id_to_delete = random.choice(delete_links)
                self.client.get(f"/delete_property/{prop_id_to_delete}", name="/delete_property/[id]")

    def full_booking_flow(self):
        """Rulează un flux complet de la căutare la anulare."""
        start_date = datetime.now().date() + timedelta(days=random.randint(200, 300))
        end_date = start_date + timedelta(days=random.randint(2, 5))
        
        with self.client.post("/search_results", data={"period": f"{start_date.isoformat()} to {end_date.isoformat()}", "destination": "Bucuresti", "adults": 1, "rooms": 1}, name="/search_results", catch_response=True) as search_response:
            property_links = re.findall(r'href="(/property/\d+\?.*?)"', search_response.text)
            if not property_links: return

            property_link = random.choice(property_links).replace("&amp;", "&")
            with self.client.get(property_link, name="/property/[id]", catch_response=True) as prop_response:
                booking_links = re.findall(r'href="(/booking/confirm\?.*?)"', prop_response.text)
                if not booking_links:
                    prop_response.success()
                    return

                booking_link = random.choice(booking_links).replace("&amp;", "&")
                room_ids = re.search(r'ids=([\d,]+)', booking_link).group(1)
                start_str = re.search(r'start=([\d-]+)', booking_link).group(1)
                end_str = re.search(r'end=([\d-]+)', booking_link).group(1)

                self.client.get(booking_link, name="/booking/confirm [GET]")
                with self.client.post("/booking/confirm", data={"room_ids": room_ids, "start_date": start_str, "end_date": end_str, "full_name": "Test User", "phone": "0712345678", "email": "test@test.com"}, name="/booking/confirm [POST]", catch_response=True, allow_redirects=False) as conf_response:
                    if conf_response.status_code == 302:
                        conf_response.success()
                        self.client.get("/booking/success", name="/booking/success")

        with self.client.get("/my-reservations", name="/my-reservations", catch_response=True) as res_response:
            if res_response.status_code == 200:
                reservation_ids = re.findall(r'href="/cancel_reservation/(\d+)"', res_response.text)
                if reservation_ids:
                    res_id = random.choice(reservation_ids)
                    self.client.get(f"/cancel_reservation/{res_id}", name="/cancel_reservation/[id]")

    def spam_static_files(self):
        """Cere toate fișierele statice pentru a stresa serverul."""
        static_files = [
            "/static/css/style_home.css", "/static/css/style_login.css",
            "/static/css/style_profile.css", "/static/css/style_admin.css",
            "/static/css/style_my_properties.css", "/static/css/style_my_reservations.css"
        ]
        for file_path in static_files:
            self.client.get(file_path, name="/static/all_css")
            
    def update_profile(self):
        """Accesează profilul și îl editează."""
        self.client.get("/profile", name="/profile")
        self.client.post("/edit-profile", data={"username": self.username, "email": f"haos_{self.username}@test.com", "current_password": self.password, "new_password": "", "confirm_new_password": ""}, name="/edit-profile")