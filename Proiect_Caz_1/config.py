import os

class Config:
    SECRET_KEY = "cheie_super_secreta_perta_proiect_v6"
    
    MASTER_DB = {
        'user': 'app_user',
        'password': 'parola_aplicatiei',
        'host': '192.168.50.1',
        'database': 'rezervari'
    }
    
    SLAVE_DB = {
        'user': 'app_user',
        'password': 'parola_aplicatiei',
        'host': '192.168.50.2',
        'database': 'rezervari'
    }
    
    DB_URL_MASTER = f"mysql+pymysql://{MASTER_DB['user']}:{MASTER_DB['password']}@{MASTER_DB['host']}/{MASTER_DB['database']}?charset=utf8mb4"
    DB_URL_SLAVE = f"mysql+pymysql://{SLAVE_DB['user']}:{SLAVE_DB['password']}@{SLAVE_DB['host']}/{SLAVE_DB['database']}?charset=utf8mb4"