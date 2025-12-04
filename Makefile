# ----------------------------------------
# Global config
# ----------------------------------------
PYTHON := python
MANAGE := $(PYTHON) manage.py

# Default host/port for runserver
HOST ?= 0.0.0.0
PORT ?= 8000

run:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=project.settings.$(CLIENT) \
		$(MANAGE) runserver $(HOST):$(PORT)

migrate:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=project.settings.$(CLIENT) \
		$(MANAGE) migrate

shell:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=project.settings.$(CLIENT) \
		$(MANAGE) shell

createsuperuser:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=project.settings.$(CLIENT) \
		$(MANAGE) createsuperuser

showmigrations:
	ENV_FILE=$(ENV_FILE) DJANGO_SETTINGS_MODULE=project.settings.$(CLIENT) \
		$(MANAGE) showmigrations


# ----------------------------------------
# Airborne (local)
# ----------------------------------------
AIRBORNE_ENV := .env.airborne_local
AIRBORNE_SETTINGS := project.settings.airborne

run-airborne:
	DJANGO_SETTINGS_MODULE=project.settings.airborne \
		$(MANAGE) runserver $(HOST):$(PORT)


migrate-airborne:
	ENV_FILE=$(AIRBORNE_ENV) DJANGO_SETTINGS_MODULE=$(AIRBORNE_SETTINGS) \
		$(MANAGE) migrate

shell-airborne:
	ENV_FILE=$(AIRBORNE_ENV) DJANGO_SETTINGS_MODULE=$(AIRBORNE_SETTINGS) \
		$(MANAGE) shell

createsuperuser-airborne:
	ENV_FILE=$(AIRBORNE_ENV) DJANGO_SETTINGS_MODULE=$(AIRBORNE_SETTINGS) \
		$(MANAGE) createsuperuser


# ----------------------------------------
# SkyGuy (local)
# ----------------------------------------
SKYGUY_ENV := .env.skyguy_local
SKYGUY_SETTINGS := project.settings.skyguy

run-skyguy:
	DJANGO_SETTINGS_MODULE=project.settings.skyguy \
		$(MANAGE) runserver $(HOST):$(PORT)

migrate-skyguy:
	ENV_FILE=$(SKYGUY_ENV) DJANGO_SETTINGS_MODULE=$(SKYGUY_SETTINGS) \
		$(MANAGE) migrate

shell-skyguy:
	ENV_FILE=$(SKYGUY_ENV) DJANGO_SETTINGS_MODULE=$(SKYGUY_SETTINGS) \
		$(MANAGE) shell

createsuperuser-skyguy:
	ENV_FILE=$(SKYGUY_ENV) DJANGO_SETTINGS_MODULE=$(SKYGUY_SETTINGS) \
		$(MANAGE) createsuperuser


# ----------------------------------------
# Demo (local)
# ----------------------------------------
DEMO_ENV := .env.demo_local
DEMO_SETTINGS := project.settings.demo

run-demo:
	ENV_FILE=$(DEMO_ENV) DJANGO_SETTINGS_MODULE=$(DEMO_SETTINGS) \
		$(MANAGE) runserver $(HOST):$(PORT)

migrate-demo:
	ENV_FILE=$(DEMO_ENV) DJANGO_SETTINGS_MODULE=$(DEMO_SETTINGS) \
		$(MANAGE) migrate

shell-demo:
	ENV_FILE=$(DEMO_ENV) DJANGO_SETTINGS_MODULE=$(DEMO_SETTINGS) \
		$(MANAGE) shell

createsuperuser-demo:
	ENV_FILE=$(DEMO_ENV) DJANGO_SETTINGS_MODULE=$(DEMO_SETTINGS) \
		$(MANAGE) createsuperuser


# ----------------------------------------
# Git + Heroku Deployment for FlightPlan
# ----------------------------------------

# Push local changes to GitHub
push-github:
	git add .
	git commit -m "update"
	git push origin main

# Deploy to Airborne Images (flightplan-airborne)
# make deploy-airborne
deploy-airborne: push-github
	git push airborne main

# Deploy to SkyGuy (flightplan-skyguy)
# make deploy-skyguy
deploy-skyguy: push-github
	git push skyguy main




#-------------------------------------------------------------------------------------------
#								C O M M A N D S 
#
# Airborne Local:
# make run-airborne          # uses .env.airborne_local + project.settings.airborne
# make migrate-airborne
# make shell-airborne
# make createsuperuser-airborne


# SkyGuy Local:
# make run-skyguy            # uses .env.skyguy_local + project.settings.skyguy
# make migrate-skyguy
# make shell-skyguy
# make createsuperuser-skyguy


# Demo Local:
# make run-demo              # uses .env.demo_local + project.settings.demo
# make migrate-demo
# make shell-demo
# make createsuperuser-demo



# Base commands:
# make run CLIENT=airborne ENV_FILE=.env.airborne_local
# make run CLIENT=skyguy   ENV_FILE=.env.skyguy_local
# make run CLIENT=demo     ENV_FILE=.env.demo_local
#
#
#-------------------------------------------------------------------------------------------