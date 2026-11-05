"""Bounded device facts. The language model describes these; it cannot change them."""
import json
import re
import unicodedata
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def folded(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if not unicodedata.combining(c))


def user_turn_message(question,device=None,weather=None,clock=None):
    """Keep changing facts in the current turn, after the saved conversation.

    Hermes hoists every system message into its system prompt regardless of
    list position. Putting runtime facts there invalidates the entire history
    prefix whenever the battery changes. JSON also keeps the spoken
    question separate from validated firmware data without delimiter spoofing.
    """
    if device is None and weather is None and clock is None:return {'role':'user','content':question}
    payload={}
    if device is not None:
        facts=device.model_dump(exclude_none=True)
        if not re.search(r'\b(?:bateria|carga|cargando|enchufad[oa]|porcentaje)\b',folded(question)):
            facts.pop('battery_percent',None);facts.pop('charging',None)
        payload['mochi_device_context']=facts
    if weather is not None:payload['weather_context']=weather['content']
    if clock is not None:payload['clock_context']=clock
    # Put the actual request last, after the supporting device facts.
    payload['question']=question
    return {'role':'user','content':json.dumps(payload,ensure_ascii=False,separators=(',',':'))}


def pet_name(value: str) -> str:
    value = unicodedata.normalize('NFC', value).strip()
    if not 1 <= len(value) <= 32 or not all(c.isalpha() or c in " '-" for c in value):
        raise ValueError('Use a name with letters, spaces, apostrophes or hyphens')
    if not any(c.isalpha() for c in value):
        raise ValueError('A name needs letters')
    return value


class DeviceContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = 'Mochi'
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    charging: bool | None = None
    trigger: str = Field(default='manual', pattern=r'^(manual|wake|followup)$')
    _name = field_validator('name')(pet_name)

    @model_validator(mode='before')
    @classmethod
    def discard_retired_care_state(cls,value):
        # Accept older firmware during OTA, but never pass its removed needs
        # to the model or keep them as part of current device context.
        if isinstance(value,dict) and 'pet' in value:
            return {key:item for key,item in value.items() if key!='pet'}
        return value

    @classmethod
    def from_header(cls, value: str | None):
        if value is None:
            return None
        if len(value) > 2048:
            raise ValueError('Device context is too large')
        # ESP-IDF transmits JSON names as UTF-8; ASGI exposes raw header bytes as Latin-1.
        if not value.isascii():
            try:
                value=value.encode('latin-1').decode('utf-8')
            except (UnicodeEncodeError,UnicodeDecodeError):
                pass
        return cls.model_validate_json(value)

    def question(self, text: str):
        if self.trigger != 'wake':
            return text.strip()
        # Only remove an initial complete name, never occurrences in a question.
        return re.sub(r'^\s*' + re.escape(self.name) + r'(?!\w)[\s,.:;!?¡¿-]*', '', text,
                      count=1, flags=re.IGNORECASE).strip()

    def answer(self,text):
        """Direct device facts come from firmware, never a model's imagination."""
        query=' '.join(re.sub(r'[¿?¡!.,;:]',' ',folded(text)).split())
        prefix=folded(self.name)+' '
        if query.startswith(prefix):query=query[len(prefix):]
        query=re.sub(r'^(?:dime |puedes decirme |me dices )','',query)
        query=re.sub(r' por favor$','',query)
        if re.fullmatch(r'(?:como te llamas|cual es tu nombre)(?: ahora)?',query):
            return {'text':f'Me llamo {self.name}.','emotion':'happy'}
        if re.fullmatch(r'(?:cuanta bateria (?:tienes|te queda)|que bateria tienes|como vas de bateria)',query):
            text='Ahora no tengo una lectura de batería.' if self.battery_percent is None else f'Me queda un {self.battery_percent} por ciento de batería.'
            return {'text':text,'emotion':'idle'}
        return None
