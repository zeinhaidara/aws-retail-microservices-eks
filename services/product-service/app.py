import json
import os
from functools import lru_cache
from http.server import ThreadingHTTPServer
from metrics import MetricsHandler
from urllib.parse import urlparse


SERVICE = "product-service"
PORT = int(os.getenv("PORT", "8080"))

PRODUCTS = {
    "orbit-001": {"productId": "orbit-001", "name": "Lunar Far Side", "price": 249000.00, "category": "Moon · 8 days", "description": "Loop around the Moon and see the far side on a close-to-home orbital escape.", "image": "moon", "durationDays": 8, "bestMonth": "June"},
    "orbit-002": {"productId": "orbit-002", "name": "Red Planet Passage", "price": 890000.00, "category": "Mars · 21 days", "description": "A cinematic Mars transfer concept with orbital observation and a guided return itinerary.", "image": "mars", "durationDays": 21, "bestMonth": "September"},
    "orbit-003": {"productId": "orbit-003", "name": "Jupiter & Europa Explorer", "price": 1250000.00, "category": "Jupiter · 34 days", "description": "Explore Jupiter's cloud bands and Europa's ice-bright horizon from a deep-space viewing route.", "image": "jupiter", "durationDays": 34, "bestMonth": "November"},
    "orbit-004": {"productId": "orbit-004", "name": "Mercury Solar Pass", "price": 399000.00, "category": "Mercury · 15 days", "description": "A close solar-system route with a protected orbital viewing pass by the smallest planet.", "image": "mercury", "durationDays": 15, "bestMonth": "March"},
    "orbit-005": {"productId": "orbit-005", "name": "Venus Cloudline", "price": 475000.00, "category": "Venus · 19 days", "description": "Take in the bright cloud tops of Venus from a high-altitude observation orbit.", "image": "venus", "durationDays": 19, "bestMonth": "April"},
    "orbit-006": {"productId": "orbit-006", "name": "Earth Orbital Retreat", "price": 99000.00, "category": "Earth orbit · 3 days", "description": "A premium low-Earth-orbit stay with aurora views, sunrise passes, and a guided return.", "image": "earth", "durationDays": 3, "bestMonth": "May"},
    "orbit-007": {"productId": "orbit-007", "name": "Saturn Ring Odyssey", "price": 1450000.00, "category": "Saturn · 45 days", "description": "A long-range Saturn flyby concept framed by the planet's iconic rings.", "image": "saturn", "durationDays": 45, "bestMonth": "October"},
    "orbit-008": {"productId": "orbit-008", "name": "Uranus Blue Frontier", "price": 1800000.00, "category": "Uranus · 62 days", "description": "A far-frontier tour to Uranus with a cool blue atmospheric panorama.", "image": "uranus", "durationDays": 62, "bestMonth": "January"},
    "orbit-009": {"productId": "orbit-009", "name": "Neptune Deep Blue", "price": 2050000.00, "category": "Neptune · 78 days", "description": "A deep-space passage to Neptune for an extended view of the outermost planet.", "image": "neptune", "durationDays": 78, "bestMonth": "December"},
    "orbit-010": {"productId": "orbit-010", "name": "Solar Grand Tour", "price": 3250000.00, "category": "Sun orbit · 52 days", "description": "A fictional heliocentric grand tour tracing a sweeping orbit around the Sun with planetary flybys.", "image": "sun", "durationDays": 52, "bestMonth": "July"},
}
VALKEY_HOST = os.getenv("VALKEY_HOST", "")
VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))
VALKEY_TLS = os.getenv("VALKEY_TLS", "true").lower() == "true"


@lru_cache(maxsize=1)
def cache_client():
    if not VALKEY_HOST:
        return None
    import redis

    return redis.Redis(
        host=VALKEY_HOST,
        port=VALKEY_PORT,
        ssl=VALKEY_TLS,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def cached_product(product_id):
    client = cache_client()
    if client:
        try:
            cached = client.get(f"product:{product_id}")
            if cached:
                return json.loads(cached)
        except Exception as error:
            print(f"Valkey read failed; using catalog source: {error}")
    product = PRODUCTS.get(product_id)
    if product and client:
        try:
            client.setex(f"product:{product_id}", 60, json.dumps(product))
        except Exception as error:
            print(f"Valkey write failed; using catalog source: {error}")
    return product


def cached_catalog():
    client = cache_client()
    if client:
        try:
            cached = client.get("product:catalog")
            if cached:
                return json.loads(cached)
        except Exception as error:
            print(f"Valkey read failed; using catalog source: {error}")
    items = list(PRODUCTS.values())
    if client:
        try:
            client.setex("product:catalog", 60, json.dumps(items))
        except Exception as error:
            print(f"Valkey write failed; using catalog source: {error}")
    return items



class Handler(MetricsHandler):
    def _write(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/health":
            return self._write(200, {"status": "ok", "service": SERVICE})
        if path == "/ready":
            return self._write(200, {"status": "ready", "service": SERVICE})

        if path == "/products":
            return self._write(200, {"items": cached_catalog()})
        if path.startswith("/products/"):
            product = cached_product(path.split("/")[-1])
            return self._write(200, product) if product else self._write(404, {"error": "product not found"})


        return self._write(404, {"error": "not found"})



if __name__ == "__main__":
    print(f"Starting {SERVICE} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
