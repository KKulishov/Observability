#!/bin/bash
set -e

if [[ ! -z "$1" ]]; then
    echo ${*}
    exec  ${*}
else
    #exec /usr/local/bin/opentelemetry-instrument --traces_exporter otlp --service_name productpage python /opt/microservices/productpage.py 9080 
    python /opt/microservices/productpage.py 9080
fi
