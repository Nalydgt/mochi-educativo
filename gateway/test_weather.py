from datetime import datetime, timezone
from pathlib import Path
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from app import Settings, LocationInput, create_app
from weather import WeatherService, weather_question

NOW = datetime(2026,10,21,0,30,tzinfo=timezone.utc)
AUTH = {"Authorization":"Bearer " + "a"*40}


def forecast_data(day="2026-10-21"):
    return {"timezone":"Europe/Madrid","utc_offset_seconds":7200,
        "current":{"temperature_2m":18}, "daily":{"time":[day],"weather_code":[2],
        "temperature_2m_min":[12],"temperature_2m_max":[22],
        "precipitation_probability_max":[30],"wind_speed_10m_max":[16]}}


class Brain:
    def __init__(self): self.calls=[]
    def ready(self): return True
    def reply(self,messages):
        self.calls.append(messages)
        return {"text":"Según Open-Meteo, hoy habrá entre 12 y 22 grados.","emotion":"happy"}


class Speech:
    def transcribe(self,pcm): return "¿Qué tiempo va a hacer hoy?"
    def speak(self,text): return b"\x01\x02"*1600


def test_forecast_uses_rounded_gps_coordinates_and_reuses_recent_data():
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.params["latitude"] == "40.42"
        assert request.url.params["longitude"] == "-3.7"
        assert request.url.params["timezone"] == "auto"
        return httpx.Response(200,json=forecast_data())
    service=WeatherService(httpx.MockTransport(handler),clock=lambda:NOW)
    location=LocationInput(latitude=40.4168,longitude=-3.7038)
    context=service.context("¿Qué tiempo hace hoy?",location)
    assert context["status"] == "ready" and context["position"]["source"] == "gps"
    assert context["forecast"]["local_date"] == "2026-10-21"
    service.context("¿Y lloverá mañana?",location)
    assert len(calls)==1


@pytest.mark.parametrize('payload', [[], None, {'current': []}, {'daily': []}])
def test_malformed_provider_data_returns_unavailable(payload):
    data = {**forecast_data(), **payload} if isinstance(payload, dict) else payload
    service = WeatherService(httpx.MockTransport(lambda request: httpx.Response(200, json=data)), clock=lambda: NOW)
    assert service.context('¿Qué tiempo hace hoy?', LocationInput(latitude=40, longitude=-3)) == {'status': 'unavailable'}
    service.close()


def test_malformed_geocoding_returns_unavailable():
    service = WeatherService(httpx.MockTransport(lambda request: httpx.Response(200, json=[])), clock=lambda: NOW)
    assert service.context('¿Qué tiempo hace en Valencia hoy?', None) == {'status': 'unavailable'}
    service.close()


def test_midnight_invalidates_previous_day_forecast():
    now=[datetime(2026,10,20,21,59,tzinfo=timezone.utc)]
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json=forecast_data("2026-10-20" if len(calls)==1 else "2026-10-21"))
    service=WeatherService(httpx.MockTransport(handler),clock=lambda:now[0])
    service.forecast(40,-3)
    now[0]=datetime(2026,10,20,22,1,tzinfo=timezone.utc)
    assert service.forecast(40,-3)["local_date"]=="2026-10-21" and len(calls)==2


def test_named_city_takes_priority_over_device_gps():
    def handler(request):
        if request.url.host.startswith("geocoding"):
            assert request.url.params["name"] == "Valencia"
            return httpx.Response(200,json={"results":[{"name":"Valencia","latitude":39.47,"longitude":-.38,"country_code":"ES"}]})
        assert request.url.params["latitude"] == "39.47"
        return httpx.Response(200,json=forecast_data())
    service=WeatherService(httpx.MockTransport(handler),clock=lambda:NOW)
    context=service.context("¿Qué tiempo hace en Valencia hoy?",LocationInput(latitude=40,longitude=-3))
    assert context["position"]["source"]=="named_place" and context["position"]["name"]=="Valencia"


def test_weather_followup_and_time_duration_are_distinct():
    assert weather_question("¿Y mañana?",[{"role":"user","content":"¿Va a llover hoy?"}])
    assert not weather_question("¿Cuánto tiempo tardas en hablar?")
    assert not weather_question("¿Y mañana?",[{"role":"user","content":"Hola"}])


@pytest.mark.parametrize('question',[
    '¿Qué temperatura hace en mi habitación?',
    '¿Qué es la humedad?',
    '¿Por qué llueve?',
    '¿A qué temperatura hierve el agua?',
    'Tengo frío.',
    'Me gusta la lluvia.'])
def test_weather_keywords_do_not_hijack_general_or_indoor_conversations(question):
    assert not weather_question(question)


def test_current_weather_still_requests_real_forecast():
    for question in ('¿Va a llover hoy?', '¿Qué tiempo hace hoy?', '¿Hará frío mañana?',
                     'Me gusta la lluvia, ¿va a llover hoy?'):
        assert weather_question(question)


def test_no_gps_does_not_ask_user_where_they_are(tmp_path):
    brain=Brain()
    client=TestClient(create_app(Settings("a"*40,tmp_path,Path("unused")),brain,Speech()))
    response=client.post("/v1/chat",headers=AUTH,json={"text":"¿Qué tiempo hace hoy?"})
    assert response.status_code==200 and "GPS" in response.json()["text"]
    assert "dónde" not in response.json()["text"] and not brain.calls


def test_voice_weather_requests_a_gps_fix_only_when_needed(tmp_path):
    brain=Brain()
    client=TestClient(create_app(Settings('a'*40,tmp_path,Path('unused')),brain,Speech()))
    response=client.post('/v1/turn',headers={**AUTH,'Content-Type':'application/octet-stream'},
        content=b'\x01\x02'*3200)
    assert response.status_code==200
    assert response.headers['X-Mochi-Request-GPS']=='1'
    assert not brain.calls


def test_voice_turn_passes_current_forecast_but_does_not_store_coordinates(tmp_path):
    service=WeatherService(httpx.MockTransport(lambda request:httpx.Response(200,json=forecast_data())),clock=lambda:NOW)
    brain=Brain()
    app=create_app(Settings("a"*40,tmp_path,Path("unused")),brain,Speech(),service)
    client=TestClient(app)
    headers={**AUTH,"Content-Type":"application/octet-stream","X-Mochi-Latitude":"40.4168",
        "X-Mochi-Longitude":"-3.7038","X-Mochi-Location-Age":"600","X-Mochi-Location-Current":"0"}
    response=client.post("/v1/turn",headers=headers,content=b"\x00\x00"*16000)
    assert response.status_code==200 and response.headers["x-mochi-sample-rate"]=="16000"
    current=json.loads(brain.calls[-1][-1]['content'])
    assert "last_known_gps" in current['weather_context']
    assert "Open-Meteo" in current['weather_context']
    assert not any(m['role']=='system' for m in brain.calls[-1])
    assert "40.4168" not in json.dumps(app.state.memory.history("mochi"))
    assert len(app.state.memory.history("mochi"))==2
    assert client.get("/v1/weather").status_code==401
    assert client.get("/v1/weather",headers=headers).json()["ready"]


@pytest.mark.parametrize("location",[
    {"latitude":91,"longitude":0},{"latitude":0,"longitude":181},
    {"latitude":0,"longitude":0,"age_seconds":86401}])
def test_invalid_or_too_old_location_is_rejected(tmp_path,location):
    client=TestClient(create_app(Settings("a"*40,tmp_path,Path("unused")),Brain(),Speech()))
    assert client.post("/v1/chat",headers=AUTH,json={"text":"El tiempo hoy","location":location}).status_code==422


def test_unavailable_forecast_cannot_be_hallucinated_by_the_model(tmp_path):
    service=WeatherService(httpx.MockTransport(lambda request:httpx.Response(503)),clock=lambda:NOW)
    brain=Brain()
    client=TestClient(create_app(Settings("a"*40,tmp_path,Path("unused")),brain,Speech(),service))
    response=client.post("/v1/chat",headers=AUTH,json={"text":"¿Va a llover hoy?","location":{"latitude":40,"longitude":-3}})
    assert response.status_code==200 and "previsión" in response.json()["text"]
    assert not brain.calls
