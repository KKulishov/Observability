#FROM docker.io/istio/examples-bookinfo-productpage-v1:1.17.0
FROM docker.io/istio/examples-bookinfo-productpage-v1:1.19.0

#ENV HTTPS_PROXY http://proxy-server.xxx.group:3128
#ENV HTTP_PROXY http://proxy-server.xxx.group:3128
#ENV https_proxy http://proxy-server.xxx.group:3128
#ENV http_proxy http://proxy-server.xxx.group:3128
#ENV NO_PROXY "127.0.0.1, localhost, .xxx.group,minio, .xxx.ru, *.svc.cluster.local"
#ENV no_proxy "127.0.0.1, localhost, .xx.group,minio, .xxx.ru, *.svc.cluster.local"


USER root

RUN groupadd -g 1000 python
RUN useradd -s /bin/bash -g python -u 1000 -g 1000 python

#RUN apt update && apt install curl -y

WORKDIR /opt/microservices

COPY requirements.txt /opt/microservices/
RUN https_proxy=http://proxy-server.xxx.group:3128 pip install -r requirements.txt

RUN https_proxy=http://proxy-server.xxx.group:3128 pip3 install pyroscope-io

RUN https_proxy=http://proxy-server.xxx.group:3128 pip3 install pyroscope-otel opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-flask opentelemetry-exporter-otlp-proto-grpc

COPY ./lib /opt/microservices/lib/
COPY productpage.py /opt/microservices/

RUN chown -R 1000:1000 /opt/microservices

COPY entrypoint.sh /opt/microservices/entrypoint.sh 

RUN chmod +x /opt/microservices/entrypoint.sh && chown -R 1000:1000 /opt/microservices/entrypoint.sh

ENTRYPOINT ["/opt/microservices/entrypoint.sh"]
#CMD ["gunicorn", "-b", "[0.0.0.0]:9080", "productpage:app", "-w", "8", "--keep-alive", "2", "-k", "gevent"]

USER 1000
