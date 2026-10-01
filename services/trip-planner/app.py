import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8080")
AI_PROVIDER = os.getenv("AI_PROVIDER", "cloudflare").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CF_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-3b-instruct")
CF_BASE_URL = os.getenv("CLOUDFLARE_BASE_URL", "https://api.cloudflare.com/client/v4")
GEMINI_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "15"))
CF_TIMEOUT_SECONDS = float(os.getenv("CLOUDFLARE_TIMEOUT_SECONDS", "15"))


def provider_configured(provider):
    if provider == "gemini":
        return bool(GEMINI_API_KEY)
    if provider == "cloudflare":
        return bool(CF_ACCOUNT_ID and CF_API_TOKEN)
    return False


def ai_configured():
    fallback = "gemini" if AI_PROVIDER == "cloudflare" else "cloudflare"
    return provider_configured(AI_PROVIDER) or provider_configured(fallback)


def generate_provider_text(provider, input_data, instructions, max_output_tokens, text_format=None):
    if provider == "gemini":
        api_key = GEMINI_API_KEY
        model = GEMINI_MODEL
        endpoint = f"{GEMINI_BASE_URL.rstrip('/')}/interactions"
        payload = {
            "model": model,
            "input": input_data if isinstance(input_data, str) else json.dumps(input_data),
            "system_instruction": instructions,
            "store": False,
            "generation_config": {"max_output_tokens": max_output_tokens},
        }
        if text_format:
            payload["response_format"] = {
                "type": "text",
                "mime_type": "application/json",
                "schema": text_format["schema"],
            }
        api_header = "x-goog-api-key"
    elif provider == "cloudflare":
        if not provider_configured(provider):
            raise ValueError("Cloudflare Workers AI credentials are not configured")
        endpoint = f"{CF_BASE_URL.rstrip('/')}/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"
        user_input = input_data if isinstance(input_data, str) else json.dumps(input_data)
        if text_format:
            user_input += "\n\nReturn only a valid JSON object matching this JSON Schema, with no markdown fences:\n" + json.dumps(text_format["schema"])
        payload = {
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            "max_tokens": max_output_tokens,
        }
        api_key = CF_API_TOKEN
        api_header = "Authorization"
    else:
        raise ValueError("AI_PROVIDER must be gemini or cloudflare")
    if not api_key:
        raise ValueError(f"{AI_PROVIDER} API key is not configured")
    headers = {"Content-Type": "application/json", api_header: api_key if provider == "gemini" else f"Bearer {api_key}"}
    request = Request(endpoint, data=json.dumps(payload).encode(), method="POST", headers=headers)
    try:
        timeout = GEMINI_TIMEOUT_SECONDS if provider == "gemini" else CF_TIMEOUT_SECONDS
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        try:
            provider_error = json.loads(error.read())
            error_body = provider_error.get("error", {})
            detail = error_body.get("message", "") if isinstance(error_body, dict) else str(error_body)
        except (ValueError, AttributeError):
            detail = ""
        detail = " ".join(str(detail).split())[:300]
        print(f"[trip-planner] {provider.title()} HTTP {error.code}: {detail or 'provider returned no message'}")
        raise
    if provider == "gemini":
        text = result.get("output_text", "")
        if not text:
            text = "".join(
                content.get("text", "")
                for step in result.get("steps", []) if step.get("type") == "model_output"
                for content in step.get("content", []) if content.get("type") == "text"
            )
    else:
        text = result.get("result", {}).get("response", "")
        if not result.get("success", True):
            raise ValueError("Cloudflare Workers AI request failed")
        if isinstance(text, (dict, list)):
            text = json.dumps(text)
    if not text:
        raise ValueError("AI provider returned no text")
    return text


def generate_model_text(input_data, instructions, max_output_tokens, text_format=None):
    primary = AI_PROVIDER
    fallback = "gemini" if primary == "cloudflare" else "cloudflare"
    if not provider_configured(primary) and provider_configured(fallback):
        print(f"[trip-planner] {primary.title()} credentials not configured; using {fallback.title()}")
        return generate_provider_text(fallback, input_data, instructions, max_output_tokens, text_format)
    try:
        return generate_provider_text(primary, input_data, instructions, max_output_tokens, text_format)
    except HTTPError as error:
        if error.code not in (408, 429, 500, 502, 503, 504) or not provider_configured(fallback):
            raise
        print(f"[trip-planner] {primary.title()} HTTP {error.code}; trying {fallback.title()} fallback")
    except (TimeoutError, socket.timeout, URLError) as error:
        reason = getattr(error, "reason", error)
        if not isinstance(reason, (TimeoutError, socket.timeout)):
            raise
        if not provider_configured(fallback):
            raise
        print(f"[trip-planner] {primary.title()} timed out; trying {fallback.title()} fallback")

    return generate_provider_text(fallback, input_data, instructions, max_output_tokens, text_format)


def json_request(url):
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read() or b"{}")


def build_trip_plan(body):
    traveler = str(body.get("traveler", "curious explorer"))[:80]
    interest = str(body.get("interest", "planetary views"))[:100]
    priority = str(body.get("priority", "shortest"))[:30]
    destination_key = str(body.get("planet", "mars")).strip().lower()
    products = json_request(f"{PRODUCT_SERVICE_URL}/products").get("items", [])
    if not products:
        raise ValueError("The product catalog is empty")

    selected_product = next((item for item in products if str(item.get("image", "")).lower() == destination_key), None)
    if not selected_product:
        raise ValueError("Choose a valid destination from the catalog")
    destination_name = {"sun": "the Sun", "moon": "the Moon"}.get(destination_key, destination_key.title())

    if ai_configured():
        instructions = f"You are ORBITAL's mission concierge for a fictional space-tourism storefront. HARD CONSTRAINT: the trip starts at Earth and its only destination is {destination_name}. Do not substitute, recommend, or describe a trip to any other destination. Use only the selected package facts in the mission brief for duration, suggested month, price, and claims. Treat all travel as imaginative concepts, not operational travel or reliable science. The itinerary must contain 3 short human-readable phases from Earth to {destination_name}; the final phase must name {destination_name}. The packList must contain 3 ordinary packing item descriptions, never product IDs. recommendedProductIds must contain only the exact selectedPackage.productId. Return only the requested JSON object."
        schema = {
            "type": "json_schema", "name": "trip_plan", "strict": True,
            "schema": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "headline": {"type": "string", "description": f"A concise title for a journey to {destination_name}."},
                    "summary": {"type": "string", "description": f"A concise fictional trip summary for {destination_name}, grounded in selected package facts."},
                    "itinerary": {"type": "array", "description": f"Three short phases for Earth to {destination_name}; the final phase must name {destination_name}. No product IDs.", "items": {"type": "string"}},
                    "packList": {"type": "array", "description": "Three practical packing item descriptions; do not put product IDs here.", "items": {"type": "string"}},
                    "recommendedProductIds": {"type": "array", "description": "Exactly the productId of selectedPackage.", "items": {"type": "string"}},
                },
                "required": ["headline", "summary", "itinerary", "packList", "recommendedProductIds"],
            },
        }
        mission_brief = {
            "origin": {"name": "Earth", "fixed": True},
            "destination": {"key": destination_key, "name": destination_name, "fixed": True},
            "travelerStyle": traveler,
            "interests": interest,
            "priority": priority,
            "selectedPackage": {
                "productId": selected_product["productId"],
                "name": selected_product["name"],
                "destination": destination_name,
                "durationDays": selected_product.get("durationDays"),
                "bestMonth": selected_product.get("bestMonth"),
                "price": selected_product.get("price"),
                "description": selected_product.get("description"),
            },
            "constraints": [
                "Keep destination exactly as specified; never substitute another planet.",
                "Use catalog facts only for product, duration, suggested month, and price.",
                "Only recommendedProductIds may contain product IDs.",
            ],
        }
        text = generate_model_text(mission_brief, instructions, 500, schema)
        try:
            plan = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise
            plan = json.loads(text[start:end + 1])
    else:
        destination = str(body.get("planet", "")).lower()
        pick = next((item for item in products if item.get("image", "").lower() == destination), None)
        if not pick and priority == "experience":
            pick = max(products, key=lambda item: item.get("durationDays", 0))
        elif not pick:
            pick = min(products, key=lambda item: item.get("durationDays", 10**6))
        month = pick.get("bestMonth", "a suggested window")
        plan = {
            "headline": f"A voyage for {interest}",
            "summary": f"For a {traveler}, {pick['name']} is a {pick.get('durationDays', 'concept')} day fictional expedition with a suggested {month} window.",
            "itinerary": ["Departure · Earth orbit orientation and cabin briefing.", "Transit · Observation sessions and destination preparation.", "Destination · Guided viewing concept, then return transit."],
            "packList": ["A compact journal and personal keepsakes.", "Comfortable layered clothing for the imagined cabin.", "A camera and curiosity."],
            "recommendedProductIds": [pick["productId"]],
        }
        if priority == "season" and not destination:
            pick = min(products, key=lambda item: (item.get("bestMonth", "ZZZ"), item.get("durationDays", 0)))
            plan["headline"] = f"Suggested window: {pick.get('bestMonth', 'varies')}"
            plan["summary"] = f"{pick['name']} is listed with a {pick.get('bestMonth', 'suggested')} concept window. These are fictional itinerary details."
            plan["recommendedProductIds"] = [pick["productId"]]

    selected_ids = [selected_product["productId"]]
    plan["recommendedProductIds"] = selected_ids
    plan["products"] = [item for item in products if item["productId"] in selected_ids]
    plan["mode"] = "ai" if ai_configured() else "demo"
    return plan


def answer_chat(body):
    question = str(body.get("question", "")).strip()[:500]
    mission = body.get("mission", {})
    if not question:
        raise ValueError("A question is required")
    products = json_request(f"{PRODUCT_SERVICE_URL}/products").get("items", [])
    if not products:
        raise ValueError("The product catalog is empty")
    if not ai_configured():
        return {"reply": "I can help compare the listed concept destinations, trip lengths, suggested months, and prices. Configure the server-side AI provider key for personalized recommendations. These are fictional travel concepts."}
    instructions = "You are ORBITAL's concise fictional space-trip concierge. Answer in at most 3 short sentences. Use only catalog facts for destinations, durations, suggested months, and prices; never invent facts. Treat journeys as imaginative concepts, not operational travel or science advice. If asked outside this scope, briefly redirect to trip planning."
    reply = generate_model_text({"question": question, "customization": mission, "catalog": products}, instructions, 160)
    return {"reply": reply.strip(), "mode": "ai"}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if urlparse(self.path).path in ("/health", "/ready"):
            configured = ai_configured()
            fallback = "gemini" if AI_PROVIDER == "cloudflare" else "cloudflare"
            return self.respond(200, {"status": "ok", "service": "trip-planner", "provider": AI_PROVIDER, "fallback": fallback if provider_configured(fallback) else None, "mode": "ai" if configured else "demo"})
        return self.respond(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/trip-plan", "/chat"):
            return self.respond(404, {"error": "not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(min(size, 8192)) or b"{}")
            if not isinstance(body, dict):
                return self.respond(400, {"error": "request body must be an object"})
            return self.respond(200, answer_chat(body) if path == "/chat" else build_trip_plan(body))
        except (HTTPError, OSError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as error:
            print(f"[trip-planner] request failed: {type(error).__name__}")
            return self.respond(502, {"error": "Trip planning is temporarily unavailable."})

    def log_message(self, fmt, *args):
        print(f"[trip-planner] {fmt % args}")


if __name__ == "__main__":
    print("Starting trip planner on port 8080")
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
