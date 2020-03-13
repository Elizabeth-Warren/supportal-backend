# Make Supportal

STAGE?=dev
INFRASTRUCTURE?=dev

install:
	pipenv install

install-gdal-ubuntu:
	sudo apt-get update -y
	sudo apt-get install -y libgdal-dev

install-dev:
	pipenv install -d

install-dev-ubuntu: install-gdal-ubuntu
	pipenv install -d

test: install-dev
	pipenv run test

install-deploy-dependencies:
	npm install

create-domain: install-deploy-dependencies
	sls create_domain -s $(STAGE) --infrastructure $(INFRASTRUCTURE)

deploy-preflight: install-deploy-dependencies
	(export STAGE=$(STAGE) && export INFRASTRUCTURE=$(INFRASTRUCTURE) && ./make-deploy-preflight)

run-preflight: deploy-preflight
	(export STAGE=$(STAGE) && export INFRASTRUCTURE=$(INFRASTRUCTURE) && ./make-run-preflight)

deploy: install-deploy-dependencies create-domain
	sls deploy -s $(STAGE) --infrastructure $(INFRASTRUCTURE)

deploy-with-preflight: install-deploy-dependencies create-domain run-preflight
	sls deploy -s $(STAGE) --infrastructure $(INFRASTRUCTURE)
	# Run the migrations again. Because migrations are idempotent it shouldn't be
	# a problem to just run them again after a deploy. This "re-run" ensures that if
	# this is your first time standing up the edge stage, the database does get
	# migrated
	sls wsgi manage -c "migrate" -s $(STAGE) --infrastructure $(INFRASTRUCTURE)
