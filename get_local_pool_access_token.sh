#!/usr/bin/env bash
set -euo pipefail

source .env
curl -XPOST -H "Content-Type: application/x-www-form-urlencoded" \
     -u <USER_NAME>:${COGNITO_LOCAL_USER_POOL_CLIENT_SECRET}  \
     https://ew-auth-local.auth.us-east-1.amazoncognito.com/oauth2/token \
     --data-urlencode grant_type=client_credentials \
     --data-urlencode client_id=<CLIENT_ID>
