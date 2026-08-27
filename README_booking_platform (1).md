# 🏨 Distributed & Scalable Web Platform for Online Reservations

**Bachelor's Thesis · University POLITEHNICA of Bucharest**

A distributed N-tier reservation platform engineered to stay fast and stable under heavy concurrent traffic — instead of falling over like a typical monolithic setup.

![Python](https://img.shields.io/badge/Python-Flask-3776AB?logo=python&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-Master--Slave-4479A1?logo=mysql&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-Load%20Balanced-009639?logo=nginx&logoColor=white)
![Locust](https://img.shields.io/badge/Load%20Tested-Locust-brightgreen)

---

## ⚡ The Headline Result

| Metric | Monolithic | Distributed | Improvement |
|---|---|---|---|
| Response latency (peak load) | ~60s | ~270ms | **222x faster** |
| Error rate under load | High | **0%** | Fully stable |

Under simulated heavy traffic, the monolithic version buckled — the distributed architecture didn't.

---

## 🧠 Why This Exists

Reservation systems die in one place: the moment everyone shows up at once. This project asks *"what actually breaks first, and how do you engineer around it?"* — then builds and load-tests the answer.

---

## 🏗️ Architecture

Three machines, connected over a private LAN, each with a distinct role:

```
                         ┌──────────────────────────────────┐
                         │              HOST                 │
              Clients ──▶│  Nginx (load balancer, Round      │
                         │  Robin) + Flask instance #1 +     │
                         │  MySQL MASTER (writes)            │
                         └───────┬─────────────────┬────────┘
                                 │                  │
                     round-robin│                  │ replication
                                 ▼                  ▼
                    ┌─────────────────────┐  ┌─────────────────────┐
                    │        VM 2          │  │        VM 1          │
                    │  Flask instance #2 +  │  │  MySQL SLAVE         │
                    │  IIS (static files)   │  │  (reads only)        │
                    └─────────────────────┘  └─────────────────────┘
```

**How it actually works:**
- **Host** runs the first Flask instance, the MySQL **Master** (handles all writes), and **Nginx** as reverse proxy + load balancer.
- **VM 1** hosts the MySQL **Slave**, replicating the Master in real time and handling all read queries.
- **VM 2** hosts a second Flask instance (for horizontal scaling) plus an **IIS** server that offloads static file delivery so Flask only handles application logic.
- Nginx distributes incoming HTTP traffic between the two Flask instances (Host + VM 2) using **Round Robin**, and automatically reroutes traffic if one instance goes down.

This setup was specifically built to stress-test failure scenarios and measure resilience under load — not just to look distributed on paper.

---

## 🔑 Core Features

- **Role-Based Access Control (RBAC)** — separate flows for clients, property owners, and admins
- **Smart recommendation engine** — suggests optimal room packages based on search parameters
- **bcrypt password hashing** — no plaintext credentials, anywhere
- **High-concurrency handling** — built and tuned specifically to survive simultaneous booking spikes

---

## 🧪 Performance Testing

Load and stress tests were run with **Locust**, simulating concurrent users hammering the booking flow, comparing the monolithic baseline against the distributed setup across throughput, latency, and error rate.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python (Flask) |
| Database | MySQL (Master-Slave replication) |
| Load Balancing | Nginx |
| Static Assets | IIS |
| Load Testing | Locust |
| Security | bcrypt |

---

## 📌 Status

Bachelor's thesis project — architecture and performance benchmarks complete.
