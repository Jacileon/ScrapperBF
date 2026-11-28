# Point d'entrée Vercel (runtime @vercel/python).
# Toute l'application (API + pages + assets) est servie par l'app ASGI FastAPI.
from backend.main import app  # noqa: F401  (ASGI app détectée par Vercel)
