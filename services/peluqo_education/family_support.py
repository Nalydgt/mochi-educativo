"""A minimal, child-confirmed family notice for explicit peer/school disclosures.

No diagnosis, sentiment inference, audio, transcript or teacher notification.
Pending consent contains only an opaque episode ID in bounded process memory.
"""
from collections import OrderedDict
import hashlib
import re
import threading
import time
import unicodedata


def normalize(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c)).split())


def explicit_peer_disclosure(text):
    value = normalize(text)
    # Do not route household harm, unsafe family recipients or fictional cases
    # into the linked-family panel. Offer a safe adult instead.
    if re.search(r"\b(?:casa|papa|mama|padres|familia|hermano|hermana|abuelo|abuela|father|mother|parents|home|family|pai|mae|casa|familia|cuento|pelicula|historia|ejemplo|story|movie|example|conto|filme|exemplo)\b", value):
        return False
    school = re.search(r"\b(?:cole|colegio|escuela|instituto|recreo|clase|aula|companeros|companeras|ninos|ninas|school|classmates|playground|escola|colegas|recreio)\b", value)
    if not school or "?" in value or "¿" in value:
        return False
    for clause in re.split(r"\bpero\b|\bbut\b|\bmas\b|[.;]", value):
        if re.search(r"\b(?:no|nunca|nadie|not|never|nobody|nao|ninguem)\b", clause):
            continue
        if re.search(r"\b(?:me (?:pegan|golpean|insultan|amenazan|acosan)|se (?:burlan|rien) de mi|me hacen bullying|(?:they|kids) (?:hit|bully|insult|threaten) me|i am being bullied|i'm being bullied|batem em mim|me insultam|gozam comigo|fazem bullying comigo)\b", clause):
            return True
    return False


def family_alerts_enabled(state):
    return (state.get("deviceSettings") or {}).get("familySupportAlertsEnabled") is True


class SupportConsent:
    def __init__(self, ttl=120, capacity=128):
        self.ttl, self.capacity = ttl, capacity
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def _key(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    def offer(self, token, signal_id, source, *, now=None):
        instant = time.monotonic() if now is None else now
        with self._lock:
            self._entries.pop(self._key(token), None)
            self._entries[self._key(token)] = (instant, {"signalId": signal_id, "source": source})
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)

    def take(self, token, question, *, now=None):
        """Only the next actual utterance can confirm an offer; unrelated talk clears it."""
        instant = time.monotonic() if now is None else now
        with self._lock:
            item = self._entries.pop(self._key(token), None)
        if not item or instant - item[0] >= self.ttl:
            return None, None
        value = " ".join(re.sub(r"[,.!¡;]", " ", normalize(question)).split())
        if value in {"si", "si avisa", "si quiero", "si por favor", "si avisa a mi familia", "puedes avisar", "quiero avisar", "yes", "yes please", "tell my family", "sim", "sim avisa"}:
            return "confirm", item[1]
        if value in {"no", "no gracias", "no avises", "no quiero", "no thank you", "nao", "nao quero"}:
            return "decline", item[1]
        return None, None

    def forget(self, token):
        with self._lock:
            self._entries.pop(self._key(token), None)

    def expire(self):
        instant = time.monotonic()
        with self._lock:
            for key in list(self._entries):
                if instant - self._entries[key][0] >= self.ttl:
                    del self._entries[key]


def support_reply(language, outcome):
    replies = {
        "es": {
            "offer": "Gracias por contármelo. No es culpa tuya. Busca a un adulto con quien te sientas a salvo. ¿Quieres que deje un aviso breve en el panel de tu familia, sin guardar esta conversación? Puedes decir sí o no.",
            "support": "Gracias por contármelo. No es culpa tuya. Busca a un adulto de confianza con quien te sientas a salvo y cuéntale lo que está pasando. Si necesitas ayuda ahora, acércate a un adulto seguro.",
            "sent": "He dejado un aviso breve en el panel familiar para que puedan hablar contigo. El aviso no incluye esta conversación ni una grabación. Si necesitas ayuda ahora, busca a un adulto con quien te sientas a salvo.",
            "declined": "De acuerdo, no enviaré ese aviso. Puedes hablar con un adulto con quien te sientas a salvo. No tienes que resolver esto a solas.",
            "unavailable": "Ahora no he podido confirmar el aviso familiar. Busca a un adulto con quien te sientas a salvo y cuéntale lo que pasa. Si necesitas ayuda, no esperes al aviso de Mochi.",
        },
        "en": {
            "offer": "Thank you for telling me. This is not your fault. Find an adult you feel safe with. Would you like me to leave a brief notice in your family panel, without saving this conversation? You can say yes or no.",
            "support": "Thank you for telling me. This is not your fault. Find a trusted adult you feel safe with and tell them what is happening. If you need help now, go to a safe adult nearby.",
            "sent": "I left a brief notice in the family panel so they can talk with you. It does not include this conversation or a recording. If you need help now, find an adult you feel safe with.",
            "declined": "All right, I will not send that notice. You can talk to an adult you feel safe with. You do not have to handle this alone.",
            "unavailable": "I could not confirm the family notice now. Tell an adult you feel safe with what is happening. If you need help, do not wait for Mochi's notice.",
        },
        "pt": {
            "offer": "Obrigado por me contares. Não é culpa tua. Procura um adulto com quem te sintas em segurança. Queres que deixe um aviso breve no painel da tua família, sem guardar esta conversa? Podes dizer sim ou não.",
            "support": "Obrigado por me contares. Não é culpa tua. Procura um adulto de confiança com quem te sintas em segurança e conta-lhe o que está a acontecer. Se precisas de ajuda agora, procura um adulto seguro próximo.",
            "sent": "Deixei um aviso breve no painel familiar para poderem falar contigo. O aviso não inclui esta conversa nem uma gravação. Se precisas de ajuda agora, procura um adulto com quem te sintas em segurança.",
            "declined": "Está bem, não enviarei esse aviso. Podes falar com um adulto com quem te sintas em segurança. Não tens de resolver isto sozinho.",
            "unavailable": "Agora não consegui confirmar o aviso familiar. Conta o que se passa a um adulto com quem te sintas em segurança. Se precisas de ajuda, não esperes pelo aviso do Mochi.",
        },
    }
    return {"text": replies.get(language, replies["es"])[outcome], "emotion": "encourage"}
