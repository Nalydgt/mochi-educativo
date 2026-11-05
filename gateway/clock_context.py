"""Trusted local calendar/time; never infer today's date from model training."""
from datetime import datetime, timedelta, timezone
import re
import unicodedata
from zoneinfo import ZoneInfo

WEEKDAYS=('lunes','martes','miércoles','jueves','viernes','sábado','domingo')
MONTHS=('enero','febrero','marzo','abril','mayo','junio','julio','agosto',
        'septiembre','octubre','noviembre','diciembre')


def normalized(text):
    text=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[¿?¡!.,;:]',' ',text).split())


class ClockService:
    def __init__(self,zone='Europe/Madrid',clock=None):
        self.zone=ZoneInfo(zone)
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def now(self):
        value=self.clock()
        if value.tzinfo is None or value.year<2024:
            raise ValueError('A trustworthy timezone-aware clock is required')
        return value.astimezone(self.zone)

    def context(self,text):
        if not re.search(r'\b(hoy|manana|ayer|fecha|hora|dia|dias|mes|ano)\b',normalized(text)):
            return None
        local=self.now()
        return {'datetime':local.isoformat(timespec='seconds'),'timezone':self.zone.key,
                'weekday':WEEKDAYS[local.weekday()],'source':'NAS system clock'}

    def answer(self,text,name='Mochi'):
        query=normalized(text)
        prefix=normalized(name)+' '
        if query.startswith(prefix):query=query[len(prefix):]
        # Full matches only: multi-part requests, hypothetical dates, weather,
        # events and requests to search must continue through Hermes.
        query=re.sub(r'^(?:dime |puedes decirme |me dices )','',query)
        query=re.sub(r' por favor$','',query)
        date=re.fullmatch(r'(?:que (?:dia|dias)(?: de la semana)? (?:es|era|sera)(?: (hoy|ayer|manana))?|'
            r'que fecha (?:es|tenemos)(?: (hoy|ayer|manana))?|'
            r'(?:a|en) que (?:dia|fecha) estamos(?: hoy)?|'
            r'cual es la fecha(?: de hoy)?|(?:hoy) que dia es)',query)
        if date:
            local=self.now()
            offset=-1 if 'ayer' in query else 1 if 'manana' in query else 0
            target=local+timedelta(days=offset)
            lead='Ayer fue' if offset<0 else 'Mañana será' if offset>0 else 'Hoy es'
            return {'text':f'{lead} {WEEKDAYS[target.weekday()]}, {target.day} de {MONTHS[target.month-1]} de {target.year}.','emotion':'idle'}
        if re.fullmatch(r'(?:(?:que hora (?:es|tienes)(?: ahora)?)|(?:la hora(?: actual)?))',query):
            return {'text':f'Son las {self.now():%H:%M}.','emotion':'idle'}
        if re.fullmatch(r'(?:en que ano estamos|que ano es(?: este)?)',query):
            return {'text':f'Estamos en {self.now().year}.','emotion':'idle'}
        if re.fullmatch(r'(?:en que mes estamos|que mes es(?: este)?)',query):
            return {'text':f'Estamos en {MONTHS[self.now().month-1]}.','emotion':'idle'}
        return None
