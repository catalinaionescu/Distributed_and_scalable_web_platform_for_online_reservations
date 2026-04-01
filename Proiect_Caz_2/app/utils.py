from flask import session
from datetime import date
import socket
import itertools

def is_logged_in():
    return 'user_id' in session

def format_ro_date(value):
    if not isinstance(value, date): return value
    luni = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie"]
    return f"{value.day:02d} {luni[value.month - 1]} {value.year}"

def check_server_status(host, port):
    """Verifică dacă un server este online la un host și port specificat."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            return '<span style="color: green;">Online</span>'
        else:
            return '<span style="color: red;">Offline</span>'
    except socket.gaierror:
        return '<span style="color: orange;">IP Invalid</span>'
    finally:
        sock.close()

def get_recommendations(room_groups, requested_adults, requested_rooms_count):
    all_available_rooms = [group for group in room_groups for _ in range(group['count'])]
    single_room_options = []
    for room in all_available_rooms:
        if room['capacity'] >= requested_adults:
            single_room_options.append([room])
    if single_room_options:
        valid_combinations = single_room_options
    else:
        valid_combinations = []
        max_rooms_to_check = requested_rooms_count + 1
        for i in range(2, max_rooms_to_check + 1):
            for combo in itertools.combinations(all_available_rooms, i):
                if sum(room['capacity'] for room in combo) >= requested_adults:
                    valid_combinations.append(list(combo))
    if not valid_combinations: return None
    recommendations = []
    processed_combos = set()
    for combo in valid_combinations:
        combo_key = frozenset(room['name'] for room in combo)
        processed_key = (len(combo), combo_key)
        if processed_key in processed_combos: continue
        processed_combos.add(processed_key)
        total_price = sum(room['price'] for room in combo)
        total_capacity = sum(room['capacity'] for room in combo)
        room_count = len(combo)
        score = (room_count != requested_rooms_count, total_capacity - requested_adults, total_price)
        package = {"rooms": {}, "total_price": total_price, "room_ids_to_book": [], "room_count": room_count, "sort_score": score}
        summary = {}
        temp_room_ids = {group['name']: group['room_ids'].split(',') for group in room_groups if group.get('room_ids')}
        package_room_ids = []
        is_package_valid = True
        for room in combo:
            room_name = room['name']
            if temp_room_ids.get(room_name) and temp_room_ids[room_name]:
                package_room_ids.append(temp_room_ids[room_name].pop(0))
            else:
                is_package_valid = False
                break
            if room_name not in summary:
                summary[room_name] = {'count': 0, 'capacity': room['capacity']}
            summary[room_name]['count'] += 1
        if is_package_valid:
            package['room_ids_to_book'] = package_room_ids
            package['rooms'] = summary
            recommendations.append(package)
    recommendations.sort(key=lambda x: x['sort_score'])
    return recommendations[:5]