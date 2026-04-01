Scalable Platform for Online Reservations 🏨
This repository contains my bachelor's thesis project, presented at the National University of Science and Technology POLITEHNICA Bucharest (UPB). The project is a multi-user web application designed for reservation management, with the main objective of implementing and testing scalable, highly available cloud / on-premise solutions.

The system prevents server overload during peak traffic periods through an N-Tier distributed multi-node architecture.

🛠 Tech Stack
Backend: Python (Flask micro-framework)

Database: MySQL with a Master-Slave replication architecture (for efficient separation of read and write operations)

Load Balancing & Reverse Proxy: Nginx (Round Robin algorithm)

Static File Serving: IIS (Internet Information Services) web server

Performance Testing: Locust (for concurrent load testing and response time analysis)

✨ Key Features
Security: Secure authentication and user management system using bcrypt for password hashing.

Multiple Roles: Distinct dashboards and functionalities for clients (profile & reservation management), property owners (property & room management), and administrators (system-wide statistics).

Recommendation Engine: Custom internal logic that suggests and allocates optimal room packages based on the client's search criteria.

Resilience: The distributed architecture and load balancing mechanism ensure connection stability and prevent bottlenecks when handling a high volume of concurrent HTTP requests.
