Overview
This repository contains the source code and infrastructure configuration for a distributed N-tier web application designed for high-availability reservation management. The system is engineered to prevent server overload during peak traffic periods by utilizing a multi-node architecture, load balancing and database replication.

System Architecture
The platform implements a horizontally scalable infrastructure designed for fault tolerance:

Traffic Distribution: Incoming HTTP requests are intercepted by Nginx acting as a reverse proxy and load balancer (using a Round Robin algorithm) to distribute the load evenly across multiple backend nodes.

Static Asset Delivery: Static files are decoupled from the core application logic and served independently via IIS to optimize bandwidth and reduce processing overhead on the Python servers.

Data Persistence: The database layer utilizes a MySQL Master-Slave replication topology. This architecture separates heavy read operations from write operations to ensure high availability and prevent database locks under concurrent load.

Tech Stack
Backend Application: Python (Flask micro-framework)

Database: MySQL (Master-Slave replication)

Infrastructure & Servers: Nginx, IIS and custom cloud nodes

Performance Testing: Locust

Security: bcrypt for cryptographic password hashing

Core Technical Features
Role-Based Access Control (RBAC): Secure authentication and authorization flow isolated for distinct user entities: clients, property owners and administrators.

Algorithmic Allocation: A custom recommendation engine that processes user search parameters to dynamically calculate and suggest optimal room packages.

High Concurrency Handling: The distributed setup ensures connection stability and prevents request bottlenecks when handling a massive volume of concurrent HTTP traffic.

Load Testing & Profiling: The system's resilience, throughput and response times were aggressively tested and benchmarked using Locust to simulate real-world high-stress scenarios.
