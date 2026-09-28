import os

ENV = "ENV"
ENV_LOCAL = "LOCAL"
ENV_DEV = "DEV"
ENV_TEST = "TEST"
ENV_PROD = "PRO"
APOLLO_LOCAL = "http://apollo-config.example.com"
APOLLO_DEV = "http://apollo-service-apollo-configservice.apollo:8080"
APOLLO_TEST = "http://apollo-service-apollo-configservice.apollo:8080"
APOLLO_PROD = "http://apollo-service-apollo-configservice.apollo:8080"

mapping = {
    ENV_LOCAL: APOLLO_LOCAL,
    ENV_DEV: APOLLO_DEV,
    ENV_TEST: APOLLO_TEST,
    ENV_PROD: APOLLO_PROD,
}

APP_ENV = os.environ.get(ENV, ENV_LOCAL).upper()
APOLLO_URL = mapping[APP_ENV]
