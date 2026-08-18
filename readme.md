# SurgePass

**SurgePass** is a high-concurrency ticketing platform designed to handle **flash ticket sales and sudden traffic spikes**.

The project focuses on building a backend that remains reliable when thousands of users attempt to purchase a limited number of tickets at the same time.

## 🎯 Goals

* Handle high-concurrency ticket purchases
* Prevent overselling tickets
* Maintain consistency under heavy load
* Design reliable reservation and payment flows
* Explore caching, queues, rate limiting, and concurrency control
* Measure and improve system performance under load

## 🏗️ Core Features

* Event and ticket management
* Limited-inventory ticket sales
* Ticket reservation and expiry
* Concurrent purchase handling
* Payment integration
* Idempotent order processing
* Rate limiting
* Background job processing
* Load testing and performance benchmarking

## 🛠️ Tech Stack

* **Backend:** FastAPI
* **Database:** PostgreSQL
* **Cache:** Redis
* **Background Jobs:** Celery
* **Containerization:** Docker

## 🚀 Project Status

**In development.**

The project is being built incrementally with a focus on understanding and solving the distributed-systems and concurrency challenges involved in flash sales.
