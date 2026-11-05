"""Live written dialogue with a fictional device; no audio or transcripts exported."""
import json
from pathlib import Path
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web' if (ROOT / 'web').is_dir() else ROOT.parent / 'peluqo-mundos'

def main():
    device = json.loads((WEB / '.runtime/mochi-education-device.json').read_text())
    assert device.get('learnerId') == '7477fa74-aa28-4924-8fd3-6a0e5488a431', 'Use only the known fictional device'
    rows = []
    with httpx.Client(timeout=60) as client:
        for question in ('Hoy aprendí que los peces respiran por branquias. Hazme una pregunta para que te lo enseñe.',
                         'Ponme otro ejemplo de ese tema.'):
            response = client.post('http://127.0.0.1:54321/v1/education/text',
                headers={'Authorization': 'Bearer ' + device['token']},
                json={'requestId': str(uuid4()), 'question': question})
            data = response.json()
            rows.append({'status': response.status_code, 'kind': data.get('kind'),
                         'channel': data.get('channel'), 'replyCharacters': len(data.get('text', ''))})
            assert response.status_code == 200 and data.get('kind') == 'daily', 'Written dialogue unavailable'
            assert data.get('channel') == 'text' and 1 <= len(data['text']) <= 700
            assert response.headers.get('cache-control') == 'no-store'
    report = {'passed': True, 'input': 'fictional_demonstration', 'source': 'real_authenticated_text_route_and_model',
              'audioUsed': False, 'transcriptExported': False, 'externalNotificationsSent': False, 'turns': rows}
    (ROOT / 'docs/mediciones/20261106-mochi-text-conversation-live.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
