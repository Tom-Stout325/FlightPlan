![Custom Django Admin](static/images/14_d.png)



<h1 align="center">FlightPlan</h1>

<h4 align="center">Drone Operations and Financial Management for Small Businesses</h4>

> 🚀 Overview
This project is a single Django codebase that serves multiple clients.
It includes two major feature sets:
FlightPlan — Drone operations, flight logs, equipment tracking, SOPs, documents, operations planning, pilot profiles.
Money — Financial management, invoices, recurring transactions, expense tracking, taxes, reports.
All clients share the same codebase but load their own branding, features, templates, and static assets using the central base.py settings and client-specific override files in project/settings/. Authentication pages look as if they are part of your website.


## Technology Stack:


> ![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=green)
![Python](https://img.shields.io/badge/Python-FFD43B?style=for-the-badge&logo=python&logoColor=blue)
![GitHub](https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-563D7C?style=for-the-badge&logo=bootstrap&logoColor=white)
![HTML](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)
![Markdown](https://img.shields.io/badge/Markdown-000000?style=for-the-badge&logo=markdown&logoColor=white)  



___


<h1 align="center">Links</h1>

* Working Demo:  https://customadmin-88ab3088a590.herokuapp.com
    * Login:      guest
    * password:   guest12345
* Jazzmin Package:  https://django-jazzmin.readthedocs.io

___


<h1 align="center">Screenshots</h1>

> ![Default Login](static/images/Django_default_login.png)
![Custom Login](static/images/Django_custom_login.png)
![Default Admin](static/images/Django_default_admin_2.png)
![Custom Admin](static/images/Django_custom_admin.png)
![Custom Admin](static/images/Django_custom_admin_user_view.png)
![Custom Password Change](static/images/Django_custom_password_change.png)
![Drones](static/images/Django_custom_password_reset.png)


___

⚙️ Settings Structure
🧩 base.py — The One Shared Configuration
All apps (Accounts, Finance, FlightPlan) are installed here.
All clients inherit from this file.
Contains:
Django core settings
Installed apps
Template configuration
Static & media configuration
Context processors
AWS S3 configuration
Logging
Security defaults
🧩 _client.py — Client Loader
Reads the CLIENT= value from the environment and loads:
Branding metadata
PATH to clients/<client>/templates
PATH to clients/<client>/static
Feature toggles (e.g. finance module on/off)
Brand name, colors, site title, tagline
🧩 Per-client override files
Each client settings file sets only:
CLIENT
DEBUG
ALLOWED_HOSTS
Email backend (if needed)
Database (if needed)
Any client-specific overrides

___

> 🏛 Project Structure

project/
│
├── project/
│   ├── settings/
│   │   ├── base.py             ← Shared config for ALL clients
│   │   ├── _client.py          ← Loads CLIENT, BRAND, FEATURES from env
│   │   ├── airborne.py         ← Client: Airborne Images
│   │   ├── skyguy.py           ← Client: SkyGuy
│   │   ├── demo.py             ← Client: Demo instance
│   │   ├── local.py            ← Local development
│   │
│   ├── context_processors.py   ← Injects branding + client features
│   ├── urls.py
│   └── wsgi.py
│
├── accounts/      ← Auth, registration, profile setup
├── clients/       ← Client metadata models
├── finance/       ← Former “money” app (Invoices, transactions)
├── equipment/
├── flightlogs/
├── operations/
├── documents/
├── pilot/
├── help/
│
├── templates/
│   ├── index.html               ← Base template
│   ├── finance/
│   └── flightplan/
│
├── clients/
│   ├── airborne/
│   │   ├── templates/           ← Branding overrides
│   │   └── static/
│   ├── skyguy/
│   └── demo/
│
└── static/

___

🌎 Environment Variables
Each client Heroku deployment sets at least:


📌 Future Improvements
Per-client database support (optional)
Multi-tenant row-level permissioning
Shared API gateway
Background jobs (Celery + Redis)
Notifications module (email/SMS/Slack)

___



1. Big Picture: What Lives Where?
Heroku:
Ephemeral file system → anything written to disk is lost on dyno restart.
Great for staticfiles built at deploy time (via collectstatic).
NOT good for user uploads.
S3:
Persistent storage.
Ideal for media uploads (receipts, PDFs, images, etc.).
Optionally can host static files too (CSS/JS/images).
Recommended pattern for you:
Static → handled by Whitenoise on Heroku (STATIC_ROOT + collectstatic).
Media → S3 via django-storages.
You already have storages installed, so this fits perfectly.
2. AWS S3 Setup
2.1 Create the bucket
Go to S3 Console → Create bucket.
Name: something like airborne-images-media (bucket name must be globally unique).
Region: pick one close to you/Heroku (often us-east-1 works fine).
Block Public Access:
For media like receipts, incident PDFs, etc. you typically keep Block all public access = ON.
Files are then accessed via signed URLs or through your app (recommended for sensitive stuff).
Versioning: optional.
Create the bucket.
You can reuse this pattern per client (e.g., skyguy-media) or share one bucket with separate prefixes.
2.2 IAM user for Django
Go to IAM → Users → Create user.
Name: django-heroku-uploader (or similar).
Attach permissions: