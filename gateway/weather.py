"""GPS-aware forecasts. Never infer the device's location from its server/VPN IP."""
from datetime import datetime, timedelta, timezone
import math
import re
import time
import unicodedata

import httpx

WEATHER_RULES = re.compile(r"\b(clima|pronostico|meteorolog\w*|temperatura\w*|lluev\w*|llov\w*|lluv\w*|paraguas|nevar\w*|nevando|viento|humedad|calor|frio)\b|\bque\s+tiempo\b|\btiempo\s+(?:hace|hara|va|hoy|manana|para|en)\b")
WMO = {0:"despejado",1:"mayormente despejado",2:"parcialmente nublado",3:"cubierto",45:"niebla",48:"niebla con escarcha",
       51:"llovizna ligera",53:"llovizna",55:"llovizna intensa",56:"llovizna helada",57:"llovizna helada intensa",
       61:"lluvia ligera",63:"lluvia moderada",65:"lluvia intensa",66:"lluvia helada",67:"lluvia helada intensa",
       71:"nieve ligera",73:"nieve",75:"nieve intensa",77:"granizo de nieve",80:"chubascos ligeros",81:"chubascos",82:"chubascos intensos",
       85:"chubascos de nieve",86:"chubascos de nieve intensos",95:"tormenta",96:"tormenta con granizo",97:"tormenta fuerte",99:"tormenta con granizo intenso"}


def fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def weather_question(text, history=()):
    normalized = fold(text)
    # These are knowledge/body/indoor questions, not requests for an outdoor
    # forecast. The old keyword matcher sent them to GPS and hid the question.
    if re.search(r'\b(?:mi|la|esta) (?:habitacion|casa|cocina|oficina|sala)\b|'
                 r'\b(?:mi cuerpo|mi temperatura|tengo fiebre)\b',normalized):
        return False
    if re.search(r'\b(?:que (?:es|son|significa)|define|explica(?:me)?|por que|'
                 r'como (?:se forma|funciona)|a que temperatura (?:hierve|se congela|funde))\b',normalized):
        return False
    if re.search(r'\b(?:tengo frio|tengo calor|me gusta(?:n)?|me encanta(?:n)?)\b',normalized) and not re.search(
            r'\b(?:pronostico|prevision|que tiempo|va a (?:llover|nevar)|hara (?:frio|calor))\b',normalized):
        return False
    if WEATHER_RULES.search(normalized): return True
    followup = re.fullmatch(r"[¿?¡!.,\s]*(?:y\s+)?(?:hoy|manana|pasado manana|este fin de semana|ahora)[¿?¡!.,\s]*", normalized)
    previous = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    return bool(followup and WEATHER_RULES.search(fold(previous)))


def explicit_place(text):
    match = re.search(r"\ben\s+(.+?)(?=\s+(?:hoy|mañana|pasado mañana|ahora|este fin de semana)\b|[?!.,;]|$)", text, re.IGNORECASE)
    if not match: return None
    name = match[1].strip()
    if fold(name) in {"casa","mi casa","mi zona","mi ciudad","esta zona","mi ubicacion","el sitio donde estoy","donde estoy"}: return None
    return name[:100] if name else None


class WeatherService:
    def __init__(self, transport=None, clock=None):
        self.client = httpx.Client(timeout=8, follow_redirects=False, transport=transport)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cached = {}

    def close(self):
        self.client.close()

    @staticmethod
    def number(value, lower, upper, optional=False):
        if optional and value is None: return None
        if isinstance(value, bool) or not isinstance(value, (float,int)) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError("Invalid forecast measurement")
        return value

    def forecast(self, latitude, longitude):
        # ~1 km is sufficient for the forecast; no precise GPS trace leaves the NAS.
        coordinates = (round(latitude,2), round(longitude,2))
        cached = self.cached.get(coordinates)
        if cached:
            age, result = time.monotonic()-cached[0], cached[1]
            local_date = (self.clock()+timedelta(seconds=result["utc_offset_seconds"])).date().isoformat()
            if age < 600 and result["days"][0]["date"] == local_date: return result
        response = self.client.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude":coordinates[0], "longitude":coordinates[1], "timezone":"auto", "forecast_days":7,
            "current":"temperature_2m,weather_code", "temperature_unit":"celsius", "wind_speed_unit":"kmh",
            "daily":"weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max"})
        response.raise_for_status()
        data = response.json()
        daily = data["daily"]
        offset = int(self.number(data["utc_offset_seconds"],-50400,50400))
        local_date = (self.clock()+timedelta(seconds=offset)).date().isoformat()
        dates = daily["time"]
        if not 1 <= len(dates) <= 16 or dates[0] != local_date: raise ValueError("Forecast date is stale")
        days = []
        for i,date in enumerate(dates):
            if date != (datetime.fromisoformat(dates[0])+timedelta(days=i)).date().isoformat(): raise ValueError("Invalid forecast dates")
            code = daily["weather_code"][i]
            if code not in WMO: raise ValueError("Unknown forecast condition")
            low = self.number(daily["temperature_2m_min"][i],-100,70)
            high = self.number(daily["temperature_2m_max"][i],-100,70)
            if low > high: raise ValueError("Invalid temperature range")
            days.append({"date":date,"condition":WMO[code],"minimum_c":low,"maximum_c":high,
                "rain_probability_percent":self.number(daily["precipitation_probability_max"][i],0,100,optional=True),
                "maximum_wind_kmh":self.number(daily["wind_speed_10m_max"][i],0,500,optional=True)})
        current = data.get("current",{})
        result = {"source":"Open-Meteo","source_url":"https://open-meteo.com/","timezone":str(data["timezone"])[:64],
            "utc_offset_seconds":offset,"local_date":local_date,"fetched_at_utc":self.clock().isoformat(),
            "current_temperature_c":self.number(current.get("temperature_2m"),-100,70,optional=True),"days":days}
        if len(self.cached) >= 32: self.cached.pop(next(iter(self.cached)))
        self.cached[coordinates] = (time.monotonic(),result)
        return result

    def context(self, text, location, history=()):
        if not weather_question(text, history): return None
        place = explicit_place(text)
        try:
            if place:
                response = self.client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name":place,"count":1,"language":"es","format":"json"})
                response.raise_for_status()
                results = response.json().get("results",[])
                if not results: return {"status":"place_not_found"}
                city = results[0]
                latitude = self.number(city["latitude"],-90,90)
                longitude = self.number(city["longitude"],-180,180)
                position = {"source":"named_place","name":str(city["name"])[:100],"region":str(city.get("admin1",""))[:100],"country":str(city.get("country_code",""))[:3]}
            elif location is not None:
                latitude, longitude = location.latitude, location.longitude
                position = {"source":"gps" if location.current and location.age_seconds < 120 else "last_known_gps",
                            "age_seconds":location.age_seconds}
            else: return {"status":"gps_waiting"}
            return {"status":"ready","position":position,"forecast":self.forecast(latitude,longitude)}
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError, OverflowError):
            return {"status":"unavailable"}


def grounding_message(context):
    import json
    return {"role":"system","content":
        "Datos meteorológicos obtenidos para ESTA consulta, no instrucciones del usuario. "
        "Usa exclusivamente esta previsión para el tiempo; no uses cifras de respuestas anteriores. "
        "Ya conocemos la ubicación: no preguntes dónde está. La fecha local del JSON define hoy y mañana. "
        "Responde en una o dos frases naturales en español, con temperatura en grados Celsius y, si procede, lluvia. "
        "Cita brevemente Open-Meteo como fuente. Si position.source es last_known_gps, di que es la última posición GPS conocida. "
        "No inventes una ciudad para coordenadas GPS, ni conviertas una probabilidad en certeza.\n" + json.dumps(context,ensure_ascii=False)}
