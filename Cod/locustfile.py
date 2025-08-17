from locust import HttpUser, task, between, SequentialTaskSet, tag
import random
from datetime import datetime, timedelta
from lxml import html
import re

# Definim credențialele utilizatorilor pentru test.
USER_CREDENTIALS = {f"test{i}": "parola123" for i in range(1, 51)}

# Lista de orașe pentru căutări
CITIES = [
    "Bucuresti", "Cluj-Napoca", "Timisoara", "Brasov", "Sibiu",
    "Iasi", "Constanta", "Oradea", "Galati", "Craiova", ""
]

# Lista de tipuri de camere (poate fi folosită pentru un filtru)
ROOM_TYPES = [
    "Cameră Dublă Standard", "Cameră Twin", "Apartament Deluxe",
    "Garsonieră", "Cameră Triplă", "Suită Prezidențială"
]

class PropertyOwnerUser(SequentialTaskSet):
    def on_start(self):
        self.username = random.choice(list(USER_CREDENTIALS.keys()))
        self.password = USER_CREDENTIALS[self.username]
        self.client.post(
            "/login",
            {"username": self.username, "password": self.password},
            name="/login [POST]",
        )
        print(f"Property owner {self.username} logged in")

    @tag('owner_tasks')
    @task
    def add_property(self):
        with self.client.post(
            "/add_property",
            data={
                "name": f"Hotel Test {random.randint(1, 10000)}",
                "address": "Str. Test nr. 1",
                "city": "Test City",
                "country": "Test Country",
                "room_type_name[]": ["Single", "Double"],
                "room_count[]": ["2", "3"],
                "capacity[]": ["1", "2"],
                "price[]": ["100", "200"],
                "available[]": ["1", "1"],
            },
            name="/add_property [POST]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                print("Property added successfully")

    @tag('owner_tasks')
    @task
    def view_my_properties_and_reservations(self):
        with self.client.get("/my-properties", name="/my-properties [GET]", catch_response=True) as response:
            if response.status_code == 200 and "my_properties" in response.text:
                print("Successfully viewed my properties")
                property_ids = [
                    int(p.split('prop-id-')[1].split('"')[0]) for p in response.text.split("prop-id-")[1:]
                ]
                if property_ids:
                    prop_id = random.choice(property_ids)
                    self.client.get(
                        f"/manage_property_reservations/{prop_id}",
                        name="/manage_property_reservations [GET]",
                    )
                    print(f"Viewed reservations for property {prop_id}")
                else:
                    print("No properties found for owner to manage.")

    @tag('owner_tasks')
    @task
    def edit_property(self):
        with self.client.get("/my-properties", name="/my-properties [GET]", catch_response=True) as response:
            if response.status_code == 200 and "my_properties" in response.text:
                property_ids = [
                    int(p.split('prop-id-')[1].split('"')[0]) for p in response.text.split("prop-id-")[1:]
                ]
                if property_ids:
                    prop_id = random.choice(property_ids)
                    with self.client.post(
                        f"/edit_property/{prop_id}",
                        data={
                            "name": f"Edited Hotel {random.randint(1, 10000)}",
                            "address": "Str. Editata 123",
                            "city": "Edited City",
                            "country": "Edited Country",
                            "room_type_name[]": ["Single", "Double"],
                            "room_count[]": ["1", "2"],
                            "capacity[]": ["1", "2"],
                            "price[]": ["110", "220"],
                            "available[]": ["1", "1"],
                        },
                        name="/edit_property [POST]",
                        catch_response=True,
                    ) as response_edit:
                        if response_edit.status_code == 200:
                            print(f"Property {prop_id} edited successfully")
                else:
                    print("No properties found for owner to edit.")

    @tag('owner_tasks')
    @task
    def delete_property(self):
        with self.client.get("/my-properties", name="/my-properties [GET]", catch_response=True) as response:
            if response.status_code == 200:
                property_ids = [
                    int(p.split('prop-id-')[1].split('"')[0]) for p in response.text.split("prop-id-")[1:]
                ]
                if property_ids:
                    prop_id_to_delete = property_ids[0]
                    with self.client.get(
                        f"/delete_property/{prop_id_to_delete}",
                        name="/delete_property [GET]",
                        catch_response=True,
                    ) as response_delete:
                        if response_delete.status_code == 200:
                            print(f"Property {prop_id_to_delete} deleted successfully")
                else:
                    print("No properties found for owner to delete.")

    @tag('owner_tasks')
    @task
    def stop(self):
        self.interrupt()

class WebsiteUser(SequentialTaskSet):
    def on_start(self):
        self.username = random.choice(list(USER_CREDENTIALS.keys()))
        self.password = USER_CREDENTIALS[self.username]
        self.client.post(
            "/login",
            {"username": self.username, "password": self.password},
            name="/login [POST]",
        )
        print(f"User {self.username} logged in")

    @task
    @tag('general_tasks')
    def get_home_page(self):
        self.client.get("/", name="/ [GET]")

    @task
    @tag('general_tasks')
    def search_for_properties(self):
        start_date = datetime.now().date() + timedelta(days=random.randint(1, 30))
        end_date = start_date + timedelta(days=random.randint(1, 7))
        destination = random.choice(CITIES)
        self.client.post(
            "/search_results",
            {
                "period": f"{start_date.isoformat()} to {end_date.isoformat()}",
                "destination": destination,
                "adults": random.randint(1, 4),
                "rooms": random.randint(1, 2),
            },
            name="/search_results [POST]",
        )

    @tag('general_tasks')
    @task
    def view_property_and_book(self):
        start_date = datetime.now().date() + timedelta(days=random.randint(1, 30))
        end_date = start_date + timedelta(days=random.randint(1, 7))
        destination = random.choice(CITIES)
        search_data = {
            "period": f"{start_date.isoformat()} to {end_date.isoformat()}",
            "destination": destination,
            "adults": random.randint(1, 4),
            "rooms": random.randint(1, 2),
        }
        with self.client.post(
            "/search_results",
            data=search_data,
            name="/search_results [POST]",
            catch_response=True,
        ) as search_response:
            if search_response.status_code == 200:
                # Folosim regex pentru a găsi ID-urile proprietăților
                property_ids = re.findall(r'href="/property/(\d+)"', search_response.text)
                
                if property_ids:
                    prop_id = random.choice(property_ids)
                    
                    with self.client.post(
                        f"/property/{prop_id}",
                        data=search_data,
                        name="/property/{property_id} [POST]",
                        catch_response=True,
                    ) as view_response:
                        if view_response.status_code == 200 and "recommendations" in view_response.text:
                            try:
                                room_ids_str = view_response.text.split('name="ids" value="')[1].split('"')[0]
                                start_str = view_response.text.split('name="start" value="')[1].split('"')[0]
                                end_str = view_response.text.split('name="end" value="')[1].split('"')[0]
                                with self.client.get(
                                    f"/booking/confirm?ids={room_ids_str}&start={start_str}&end={end_str}",
                                    name="/booking/confirm [GET]",
                                    catch_response=True,
                                ) as booking_page:
                                    if booking_page.status_code == 200:
                                        with self.client.post(
                                            "/booking/confirm",
                                            data={
                                                "room_ids": room_ids_str,
                                                "start_date": start_str,
                                                "end_date": end_str,
                                                "full_name": f"User {self.username}",
                                                "phone": f"0712345{random.randint(10, 99)}",
                                                "email": f"{self.username}@test.com",
                                            },
                                            name="/booking/confirm [POST]",
                                            catch_response=True,
                                        ) as confirmation_response:
                                            if confirmation_response.status_code in [200, 302]:
                                                print(f"Booking confirmed by user {self.username}")
                                                if confirmation_response.headers.get("location"):
                                                    pass
                            except IndexError:
                                print("No recommendations found for booking.")
                                return
                else:
                    print(f"No properties found for destination: {destination}. Status code: {search_response.status_code}")
                    print("----- DEBUG: Raw search results page content start -----")
                    print(search_response.text)
                    print("----- DEBUG: Raw search results page content end -----")

    @tag('general_tasks')
    @task
    def view_my_reservations_and_cancel_one(self):
        with self.client.get("/my-reservations", name="/my-reservations [GET]", catch_response=True) as response:
            if response.status_code == 200:
                print("Successfully viewed my reservations")
                reservation_ids = re.findall(r'href="/cancel_reservation/(\d+)"', response.text)
                
                if reservation_ids:
                    res_id_to_cancel = random.choice(reservation_ids)
                    with self.client.get(
                        f"/cancel_reservation/{res_id_to_cancel}",
                        name="/cancel_reservation [GET]",
                        catch_response=True,
                    ) as cancel_response:
                        if cancel_response.status_code == 200:
                            print(f"Reservation {res_id_to_cancel} cancelled successfully")
                else:
                    print("No reservations found to cancel.")
                    print("----- DEBUG: Raw my-reservations page content start -----")
                    print(response.text)
                    print("----- DEBUG: Raw my-reservations page content end -----")

    @tag('general_tasks')
    @task
    def view_profile_and_logout(self):
        self.client.get("/profile", name="/profile [GET]")
        self.client.get("/logout", name="/logout [GET]")
        self.interrupt()

class MyLocust(HttpUser):
    wait_time = between(1, 5)
    host = "http://localhost:8080"

    tasks = {
        WebsiteUser: 70,
        PropertyOwnerUser: 30,
    }