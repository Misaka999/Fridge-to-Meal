"""Local browser entry point for the Fridge-to-Meal ReAct agent."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re

from agent.session import MealSessions
from agent.tools.recipe_search import RESTRICTIONS, UNITS

ROOT = Path(__file__).resolve().parent
STREAM_TYPE = "application/x-ndjson"
TURN_ERROR = "The agent could not complete this turn. Check the server logs and try again."
ASSETS = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"),
}


class MealHandler(BaseHTTPRequestHandler):
    def respond(self, status, body, mime="application/json"):
        if mime == "application/json":
            body = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        key = self.headers.get("X-Meal-Session", "")
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            self.respond(400, {"error": "Reload the page to start a kitchen session."})
            return None
        return key

    def do_GET(self):
        if self.path in ASSETS:
            name, mime = ASSETS[self.path]
            self.respond(200, (ROOT / "web" / name).read_bytes(), mime)
        elif self.path == "/api/kitchen":
            key = self.session()
            if key:
                self.respond(200, {
                    "state": self.server.sessions.get_state(key),
                    "example": json.loads((ROOT / "examples/example_request_real.json").read_text()),
                    "units": list(UNITS), "restrictions": list(RESTRICTIONS),
                    "catalogue": self.server.catalogue,
                })
        else:
            self.respond(404, {"error": "Page not found."})

    def do_POST(self):
        if self.path != "/api/turn":
            return self.respond(404, {"error": "Page not found."})
        key = self.session()
        if not key:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 100_000:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or set(data) not in ({"message"}, {"update"}, {"recipe_id"}):
                raise ValueError()
            if "message" in data and (not isinstance(data["message"], str) or not data["message"].strip()):
                raise ValueError()
            if "update" in data and not isinstance(data["update"], dict):
                raise ValueError()
            if "recipe_id" in data and (not isinstance(data["recipe_id"],str) or not data["recipe_id"].strip()):
                raise ValueError()
        except (ValueError, UnicodeError):
            return self.respond(400, {"error": "Enter a meal request or a follow-up message."})
        if self.headers.get("Accept") == STREAM_TYPE:
            return self.stream_turn(key, data)
        try:
            run = self.server.sessions.run_turn(key, **data)
        except Exception as exc:
            self.log_error("Meal turn failed (%s)", type(exc).__name__)
            return self.respond(502, {"error": TURN_ERROR,
                                      "state": self.server.sessions.get_state(key)})
        self.respond(200, run)


    def stream_turn(self, key, data):
        self.send_response(200)
        self.send_header("Content-Type", STREAM_TYPE + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def send(kind, value):
            event = json.dumps({"type": kind, "data": value}, allow_nan=False, ensure_ascii=False)
            self.wfile.write((event + "\n").encode("utf-8"))
            self.wfile.flush()

        try:
            send("progress", "Checking your meal request…")
            try:
                run = self.server.sessions.run_turn(key, on_event=send, **data)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                self.log_error("Meal turn failed (%s)", type(exc).__name__)
                send("error", TURN_ERROR)
            else:
                send("done", run)
        except (BrokenPipeError, ConnectionResetError):
            return


def make_server(port, sessions=None, *, host="127.0.0.1", recipe_source="reviewed"):
    if recipe_source not in {"reviewed", "full"}:
        raise ValueError("Choose reviewed or full recipe search.")
    if recipe_source == "full":
        from agent.tools.full_catalogue import catalogue_info, full_search_recipes, read_source_recipe
        catalogue = catalogue_info()
        if sessions is None:
            sessions = MealSessions(search=full_search_recipes,recipe_reader=read_source_recipe,adapt_recipes=True)
    else:
        catalogue = {"mode": "reviewed", "description": "Uses the original three-recipe catalogue."}
    server = ThreadingHTTPServer((host, port), MealHandler)
    server.sessions = sessions if sessions is not None else MealSessions()
    server.catalogue = catalogue
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "8765"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--recipe-source", choices=["full", "reviewed"], default="reviewed",
                        help="Full local RecipeNLG index, or the historical three-recipe catalogue.")
    args = parser.parse_args()
    with make_server(args.port, host=args.host, recipe_source=args.recipe_source) as server:
        print(f"Fridge to Meal: http://{args.host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
