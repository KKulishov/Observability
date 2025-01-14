
from flask import Flask, request, session, render_template, redirect, jsonify
from flask_bootstrap import Bootstrap
from json2html import json2html
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import Counter, generate_latest
import asyncio
import logging
import os
import requests
import simplejson as json
import sys
###
import redis
import mysql.connector
import psycopg2
## add Pyroscope
import pyroscope
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from pyroscope.otel import PyroscopeSpanProcessor

### Add pyroscope

pyroscope.configure(
    application_name    = "my.bookinfo.app", # replace this with some name for your application
    server_address      = "http://pyroscope.pyroscope.svc.cluster.local:4040", # replace this with the address of your Pyroscope server
    sample_rate         = 100, # default is 100
    detect_subprocesses = False, # detect subprocesses started by the main process; default is False
    oncpu               = True, # report cpu time only; default is True
    gil_only            = True, # only include traces for threads that are holding on to the Global Interpreter Lock; default is True
    enable_logging      = True, # does enable logging facility; default is False
)

###########



# These two lines enable debugging at httplib level (requests->urllib3->http.client)
# You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
# The only thing missing will be the response.body which is not logged.
import http.client as http_client
http_client.HTTPConnection.debuglevel = 1

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.DEBUG)

## redis param connect
HOST_REDIS = os.getenv("HOST_REDIS")
REDIS_PASS = os.getenv("REDIS_PASS")

## mysql param connect
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

## postgresql
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_DB = os.getenv("POSTGRES_DB")

# Set the secret key to some random bytes. Keep this really secret!
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'

Bootstrap(app)

servicesDomain = "" if (os.environ.get("SERVICES_DOMAIN") is None) else "." + os.environ.get("SERVICES_DOMAIN")
detailsHostname = "details" if (os.environ.get("DETAILS_HOSTNAME") is None) else os.environ.get("DETAILS_HOSTNAME")
detailsPort = "9080" if (os.environ.get("DETAILS_SERVICE_PORT") is None) else os.environ.get("DETAILS_SERVICE_PORT")
ratingsHostname = "ratings" if (os.environ.get("RATINGS_HOSTNAME") is None) else os.environ.get("RATINGS_HOSTNAME")
ratingsPort = "9080" if (os.environ.get("RATINGS_SERVICE_PORT") is None) else os.environ.get("RATINGS_SERVICE_PORT")
reviewsHostname = "reviews" if (os.environ.get("REVIEWS_HOSTNAME") is None) else os.environ.get("REVIEWS_HOSTNAME")
reviewsPort = "9080" if (os.environ.get("REVIEWS_SERVICE_PORT") is None) else os.environ.get("REVIEWS_SERVICE_PORT")

flood_factor = 0 if (os.environ.get("FLOOD_FACTOR") is None) else int(os.environ.get("FLOOD_FACTOR"))

details = {
    "name": "http://{0}{1}:{2}".format(detailsHostname, servicesDomain, detailsPort),
    "endpoint": "details",
    "children": []
}

ratings = {
    "name": "http://{0}{1}:{2}".format(ratingsHostname, servicesDomain, ratingsPort),
    "endpoint": "ratings",
    "children": []
}

reviews = {
    "name": "http://{0}{1}:{2}".format(reviewsHostname, servicesDomain, reviewsPort),
    "endpoint": "reviews",
    "children": [ratings]
}

productpage = {
    "name": "http://{0}{1}:{2}".format(detailsHostname, servicesDomain, detailsPort),
    "endpoint": "details",
    "children": [details, reviews]
}

service_dict = {
    "productpage": productpage,
    "details": details,
    "reviews": reviews,
}

request_result_counter = Counter('request_result', 'Results of requests', ['destination_app', 'response_code'])

# A note on distributed tracing:
#
# Although Istio proxies are able to automatically send spans, they need some
# hints to tie together the entire trace. Applications need to propagate the
# appropriate HTTP headers so that when the proxies send span information, the
# spans can be correlated correctly into a single trace.
#
# To do this, an application needs to collect and propagate headers from the
# incoming request to any outgoing requests. The choice of headers to propagate
# is determined by the trace configuration used. See getForwardHeaders for
# the different header options.
#
# This example code uses OpenTelemetry (http://opentelemetry.io/) to propagate
# the 'b3' (zipkin) headers. Using OpenTelemetry for this is not a requirement.
# Using OpenTelemetry allows you to add application-specific tracing later on,
# but you can just manually forward the headers if you prefer.
#
# The OpenTelemetry example here is very basic. It only forwards headers. It is
# intended as a reference to help people get started, eg how to create spans,
# extract/inject context, etc.


propagator = B3MultiFormat()
set_global_textmap(B3MultiFormat())
provider = TracerProvider()
# Sets the global default tracer provider
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

### pyroscope
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
provider.add_span_processor(PyroscopeSpanProcessor())
###

def getForwardHeaders(request):
    headers = {}

    # x-b3-*** headers can be populated using the OpenTelemetry span
    ctx = propagator.extract(carrier={k.lower():v for k, v in request.headers})
    propagator.inject(headers, ctx)

    # We handle other (non x-b3-***) headers manually
    if 'user' in session:
        headers['end-user'] = session['user']

    # Keep this in sync with the headers in details and reviews.
    incoming_headers = [
        # All applications should propagate x-request-id. This header is
        # included in access log statements and is used for consistent trace
        # sampling and log sampling decisions in Istio.
        'x-request-id',

        # Lightstep tracing header. Propagate this if you use lightstep tracing
        # in Istio (see
        # https://istio.io/latest/docs/tasks/observability/distributed-tracing/lightstep/)
        # Note: this should probably be changed to use B3 or W3C TRACE_CONTEXT.
        # Lightstep recommends using B3 or TRACE_CONTEXT and most application
        # libraries from lightstep do not support x-ot-span-context.
        'x-ot-span-context',

        # Datadog tracing header. Propagate these headers if you use Datadog
        # tracing.
        'x-datadog-trace-id',
        'x-datadog-parent-id',
        'x-datadog-sampling-priority',

        # W3C Trace Context. Compatible with OpenCensusAgent and Stackdriver Istio
        # configurations.
        'traceparent',
        'tracestate',

        # Cloud trace context. Compatible with OpenCensusAgent and Stackdriver Istio
        # configurations.
        'x-cloud-trace-context',

        # Grpc binary trace context. Compatible with OpenCensusAgent nad
        # Stackdriver Istio configurations.
        'grpc-trace-bin',

        # b3 trace headers. Compatible with Zipkin, OpenCensusAgent, and
        # Stackdriver Istio configurations.
        # This is handled by opentelemetry above
        # 'x-b3-traceid',
        # 'x-b3-spanid',
        # 'x-b3-parentspanid',
        # 'x-b3-sampled',
        # 'x-b3-flags',

        # SkyWalking trace headers.
        'sw8',

        # Application-specific headers to forward.
        'user-agent',

        # Context and session specific headers
        'cookie',
        'authorization',
        'jwt',
    ]
    # For Zipkin, always propagate b3 headers.
    # For Lightstep, always propagate the x-ot-span-context header.
    # For Datadog, propagate the corresponding datadog headers.
    # For OpenCensusAgent and Stackdriver configurations, you can choose any
    # set of compatible headers to propagate within your application. For
    # example, you can propagate b3 headers or W3C trace context headers with
    # the same result. This can also allow you to translate between context
    # propagation mechanisms between different applications.

    for ihdr in incoming_headers:
        val = request.headers.get(ihdr)
        if val is not None:
            headers[ihdr] = val

    return headers


# The UI:
@app.route('/')
@app.route('/index.html')
def index():
    """ Display productpage with normal user and test user buttons"""
    global productpage

    table = json2html.convert(json=json.dumps(productpage),
                              table_attributes="class=\"table table-condensed table-bordered table-hover\"")

    return render_template('index.html', serviceTable=table)


@app.route('/health')
def health():
    return 'Product page is healthy'

@app.route('/redis-set')
def write_to_redis():
    # Подключаемся к Redis
    r = redis.StrictRedis(host=HOST_REDIS, port=6379, password=REDIS_PASS, decode_responses=True)

    # Записываем данные в Redis
    data = {"test1": 1, "test2": 2, "test3": 3, "test4": 4, "test5": 5,
            "test6": 6, "test7": 7, "test8": 8, "test9": 9, "test10": 10,
            "test11": 11, "test12": 12, "test13": 13, "test14": 14, "test15": 15,
            "test16": 16, "test17": 17, "test18": 18, "test19": 19, "test20": 20}

    for key, value in data.items():
        r.set(key, value)

    return 'redis data send'

@app.route('/redis-get')
def read_from_redis():
    # Подключаемся к Redis
    r = redis.StrictRedis(host=HOST_REDIS, port=6379, password=REDIS_PASS, decode_responses=True)

    # Считываем данные из Redis
    data = {}
    keys = ["test1", "test2", "test3", "test4", "test5",
            "test6", "test7", "test8", "test9", "test10",
            "test11", "test12", "test13", "test14", "test15",
            "test16", "test17", "test18", "test19", "test20"]

    for key in keys:
        value = r.get(key)
        #data[key] = int(value) if value is not None else None
        result = f'{keys}'

    return  result

###
@app.route('/postgre-set')
def postgre_set():
    dbconnect = psycopg2.connect(**{
        "dbname": POSTGRES_DB,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
        "host": POSTGRES_HOST,
        "port": "5432",
    })

    data_to_insert = [
        ('test1', 1),
        ('test2', 2),
        # Другие данные...
    ]

    with dbconnect.cursor() as cursors:
        create_table_query = """
        CREATE TABLE IF NOT EXISTS test (
            id SERIAL PRIMARY KEY,
            column_name1 VARCHAR(255),
            column_name2 INTEGER
        )
        """
        cursors.execute(create_table_query)
        dbconnect.commit()

    try:
        cursor = dbconnect.cursor()
        insert_query = 'INSERT INTO test (column_name1, column_name2) VALUES (%s, %s)'
        cursor.executemany(insert_query, data_to_insert)
        dbconnect.commit()
    finally:
        cursor.close()
        dbconnect.close()

    return 'postgres send db'


@app.route('/postgre-get')
def postgre_get():
    dbconnect = psycopg2.connect(**{
        "dbname": POSTGRES_DB,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
        "host": POSTGRES_HOST,
        "port": "5432",
    })

    with dbconnect.cursor() as cursor:
        select_query = """
        SELECT * FROM test
        """
        cursor.execute(select_query)
        rows = cursor.fetchall()
         # Преобразуем данные в список словарей
        data = [{'column_name1': row[0], 'column_name2': row[1], 'column_name3': row[2]} for row in rows]
    # Возвращаем данные в формате JSON
    return jsonify(data)


@app.route('/mysql-set')
def mysql_set():
    dbconnect = mysql.connector.connect(
        host=MYSQL_HOST,
        port=3306,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DATABASE
    )

    data_to_insert = [
        ('test1', 1),
        ('test2', 2),
        # Другие данные...
    ]

    with dbconnect.cursor() as cursors:
        create_table_query = """
        CREATE TABLE IF NOT EXISTS test (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            value INT NOT NULL
        )
        """
        cursors.execute(create_table_query)
        dbconnect.commit()

    try:
        cursor = dbconnect.cursor()
        insert_query = "INSERT INTO test (name, value) VALUES (%s, %s)"
        cursor.executemany(insert_query, data_to_insert)
        dbconnect.commit()
    finally:
        cursor.close()
        dbconnect.close()

    return 'mysql send db'


@app.route('/mysql-get')
def mysql_read():
    dbconnect = mysql.connector.connect(
        host=MYSQL_HOST,
        port=3306,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DATABASE
    )

    with dbconnect.cursor() as cursor:
        select_query = """
        SELECT * FROM test
        """
        cursor.execute(select_query)
        rows = cursor.fetchall()
         # Преобразуем данные в список словарей
        data = [{'column_name1': row[0], 'column_name2': row[1], 'column_name3': row[2]} for row in rows]
    # Возвращаем данные в формате JSON
    return jsonify(data)

@app.route('/login', methods=['POST'])
def login():
    user = request.values.get('username')
    response = app.make_response(redirect(request.referrer))
    session['user'] = user
    return response


@app.route('/logout', methods=['GET'])
def logout():
    response = app.make_response(redirect(request.referrer))
    session.pop('user', None)
    return response

# a helper function for asyncio.gather, does not return a value


async def getProductReviewsIgnoreResponse(product_id, headers):
    getProductReviews(product_id, headers)

# flood reviews with unnecessary requests to demonstrate Istio rate limiting, asynchoronously


async def floodReviewsAsynchronously(product_id, headers):
    # the response is disregarded
    await asyncio.gather(*(getProductReviewsIgnoreResponse(product_id, headers) for _ in range(flood_factor)))

# flood reviews with unnecessary requests to demonstrate Istio rate limiting


def floodReviews(product_id, headers):
    loop = asyncio.new_event_loop()
    loop.run_until_complete(floodReviewsAsynchronously(product_id, headers))
    loop.close()


@app.route('/productpage')
def front():
    product_id = 0  # TODO: replace default value
    headers = getForwardHeaders(request)
    user = session.get('user', '')
    product = getProduct(product_id)
    detailsStatus, details = getProductDetails(product_id, headers)

    if flood_factor > 0:
        floodReviews(product_id, headers)

    reviewsStatus, reviews = getProductReviews(product_id, headers)
    return render_template(
        'productpage.html',
        detailsStatus=detailsStatus,
        reviewsStatus=reviewsStatus,
        product=product,
        details=details,
        reviews=reviews,
        user=user)


# The API:
@app.route('/api/v1/products')
def productsRoute():
    return json.dumps(getProducts()), 200, {'Content-Type': 'application/json'}


@app.route('/api/v1/products/<product_id>')
def productRoute(product_id):
    headers = getForwardHeaders(request)
    status, details = getProductDetails(product_id, headers)
    return json.dumps(details), status, {'Content-Type': 'application/json'}


@app.route('/api/v1/products/<product_id>/reviews')
def reviewsRoute(product_id):
    headers = getForwardHeaders(request)
    status, reviews = getProductReviews(product_id, headers)
    return json.dumps(reviews), status, {'Content-Type': 'application/json'}


@app.route('/api/v1/products/<product_id>/ratings')
def ratingsRoute(product_id):
    headers = getForwardHeaders(request)
    status, ratings = getProductRatings(product_id, headers)
    return json.dumps(ratings), status, {'Content-Type': 'application/json'}


@app.route('/metrics')
def metrics():
    return generate_latest()


# Data providers:
def getProducts():
    return [
        {
            'id': 0,
            'title': 'The Comedy of Errors',
            'descriptionHtml': '<a href="https://en.wikipedia.org/wiki/The_Comedy_of_Errors">Wikipedia Summary</a>: The Comedy of Errors is one of <b>William Shakespeare\'s</b> early plays. It is his shortest and one of his most farcical comedies, with a major part of the humour coming from slapstick and mistaken identity, in addition to puns and word play.'
        }
    ]


def getProduct(product_id):
    products = getProducts()
    if product_id + 1 > len(products):
        return None
    else:
        return products[product_id]


def getProductDetails(product_id, headers):
    try:
        url = details['name'] + "/" + details['endpoint'] + "/" + str(product_id)
        res = requests.get(url, headers=headers, timeout=3.0)
    except BaseException:
        res = None
    if res and res.status_code == 200:
        request_result_counter.labels(destination_app='details', response_code=200).inc()
        return 200, res.json()
    else:
        status = res.status_code if res is not None and res.status_code else 500
        request_result_counter.labels(destination_app='details', response_code=status).inc()
        return status, {'error': 'Sorry, product details are currently unavailable for this book.'}


def getProductReviews(product_id, headers):
    # Do not remove. Bug introduced explicitly for illustration in fault injection task
    # TODO: Figure out how to achieve the same effect using Envoy retries/timeouts
    for _ in range(2):
        try:
            url = reviews['name'] + "/" + reviews['endpoint'] + "/" + str(product_id)
            res = requests.get(url, headers=headers, timeout=3.0)
        except BaseException:
            res = None
        if res and res.status_code == 200:
            request_result_counter.labels(destination_app='reviews', response_code=200).inc()
            return 200, res.json()
    status = res.status_code if res is not None and res.status_code else 500
    request_result_counter.labels(destination_app='reviews', response_code=status).inc()
    return status, {'error': 'Sorry, product reviews are currently unavailable for this book.'}


def getProductRatings(product_id, headers):
    try:
        url = ratings['name'] + "/" + ratings['endpoint'] + "/" + str(product_id)
        res = requests.get(url, headers=headers, timeout=3.0)
    except BaseException:
        res = None
    if res and res.status_code == 200:
        request_result_counter.labels(destination_app='ratings', response_code=200).inc()
        return 200, res.json()
    else:
        status = res.status_code if res is not None and res.status_code else 500
        request_result_counter.labels(destination_app='ratings', response_code=status).inc()
        return status, {'error': 'Sorry, product ratings are currently unavailable for this book.'}


class Writer(object):
    def __init__(self, filename):
        self.file = open(filename, 'w')

    def write(self, data):
        self.file.write(data)

    def flush(self):
        self.file.flush()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        logging.error("usage: %s port" % (sys.argv[0]))
        sys.exit(-1)

    p = int(sys.argv[1])
    logging.info("start at port %s" % (p))
    # Make it compatible with IPv6 if Linux
    if sys.platform == "linux":
        app.run(host='0.0.0.0', port=p, debug=True, threaded=True)
    else:
        app.run(host='0.0.0.0', port=p, debug=True, threaded=True)

