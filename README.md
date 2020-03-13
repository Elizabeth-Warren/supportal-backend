## Open Source Notes
This is our code for a supporter portal (aka supportal)-- we stored a product called Switchboard and an internal shifting API in this code base. We have removed some of the migrations, the tests and many of the scheduled commands in order to open source this project. This code is not intended to be cloned and re-reun ouot of the box(as it would require a little work-- we rely on some shared code libraries that are not included). I've left the set up steps, and SLS documentation for posterity in hopes that they might be useful! 

If you wanted to set things up you would need to implement a few things that we implemented in common code:

- an EmailService that sends email details of the required class are in the file services/email_service.py
- Telemetry/Metric (an optional logging service)
- get_env_var to get the environment variables
- geocode to take an address and return a lat/long
- extract_phone_number_e164 to take a phone number and get a properly formatted one
- extract_postal_code to take a zip5 string and get the right postal code


### Set up
Pipenv automatically loads env vars from a .env file. This is ignored by git to allow
you to put secrets in it. For now, we don't require any secrets for local dev, so just
copy the example file:

```bash
cp example.env .env
```

Add security credentials to your AWS account
by going to the AWS console's [security credentials section](https://console.aws.amazon.com/iam/home?region=us-east-1#/security_credentials) and include the following in your .env file:
```bash
- AWS_ACCESS_KEY_ID=dummy-access-key
- AWS_SECRET_ACCESS_KEY=dummy-access-key-secret
- AWS_DEFAULT_REGION=us-east-1
```

You will need to also install postgres, openssl, GDAL and pipenv to run:

```bash
brew install psycopg2
brew install openssl
pip3 install pipenv
brew install GDAL
```

In addition you will probably need to include openssl cofigurations:
```bash
export LDFLAGS="-L/usr/local/opt/openssl/lib"
export CPPFLAGS="-I/usr/local/opt/openssl/include"
```

### Running Locally

Start mysql:
```bash
docker-compose up -d
```

You can run any `manage` command using pipenv: `pipenv run python manage.py <command>`
For convenience, we define pipenv scripts for the most common operations:

```bash
pipenv run migrate
pipenv run server
pipenv run test
```

## Deploying with SLS
Most folks shouldn't really need to do this after we get CI/CD working,

### Installation

1. Install nodejs

        ➜  supportal git:(master) ✗ node --version
        v12.13.1

2. Install [serverless](https://serverless.com/) globally

        ➜  supportal git:(master) ✗ npm i -g serverless

        ➜  supportal git:(master) ✗ sls --version
        Framework Core: 1.58.0
        Plugin: 3.2.5
        SDK: 2.2.1
        Components Core: 1.1.2
        Components CLI: 1.4.0

3. Install our `sls` dependencies

        ➜  supportal git:(master) ✗ pwd
        /Users/peterstein/source/tc/supportal

        ➜  supportal git:(master) ✗ npm i

### Doing Deeds

To run a deploy

        ➜  supportal git:(master) ✗ sls deploy --stage dev --infrastructure dev

That command will deploy the supportal application stack in our dev environment. The supportal stack in `sls` consists of:

1. _The Server Lambda_. This is the one that actually runs the API
2. _The "Expire Assignments" Lambda_. This one runs once an hour to expire assignments
3. _The Preflight Lambda_. This one actually doesn't respond to any events. Instead we can deploy separately and invoke any commands that we need to run before deploying the application. Right now, it runs migrations. In general, only our CI/CD infrastructure will care about it.

To deploy to prod

    ➜  supportal git:(master) ✗ sls deploy --stage prod --infrastructure prod

To invoke a function remotely

    ➜  supportal git:(master) ✗ sls invoke -f expire -s dev

To invoke a django management command remotely

    ➜  supportal git:(master) ✗ sls wsgi -s dev manage -c "check --list-tags"
    admin
    caches
    compatibility
    database
    models
    staticfiles
    templates
    translation
    urls

To invoke arbitrary python remotely

    sls wsgi -s dev exec -c "from supportal.app.models.person import Person; print(Person.objects.count())"
    166595
You'll need to create a superuser for your account in the shell and make sure the user
has a corresponding APIKey.
