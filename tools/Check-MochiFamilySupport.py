"""Verify a minimal family notice with synthetic speech and existing demo accounts.

Uses the normal ASR/voice route, never a child recording. Does not play audio or
send email/push messages. Root must remove the exact fictional signal afterward;
its ID is retained only in the private report for that cleanup.
"""
import argparse
import base64
import json
from pathlib import Path
from uuid import uuid4
import wave

import httpx

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" if (ROOT / "web").is_dir() else ROOT.parent / "peluqo-mundos"


def read(name):
    return json.loads((WEB / ".runtime" / name).read_text(encoding="utf-8"))


def login(client, account, cloud):
    reply = client.post(cloud["url"] + "/auth/v1/token?grant_type=password",
        headers={"apikey": cloud["key"]}, json={"email": account["email"], "password": account["password"]})
    assert reply.status_code == 200, "Demonstration account sign-in failed"
    return reply.json()["access_token"]


def snapshot(client, base, token):
    reply = client.get(base + "/api/education/school", headers={"Authorization": "Bearer " + token})
    assert reply.status_code == 200, "Adult snapshot unavailable"
    return reply.json()


def pcm(path):
    with wave.open(str(path), "rb") as recording:
        assert (recording.getframerate(), recording.getnchannels(), recording.getsampwidth()) == (16000, 1, 2)
        return recording.readframes(recording.getnframes())


def caption(reply):
    encoded = "".join(reply.headers.get("x-mochi-caption-" + str(i), "") for i in range(1, 5))
    return base64.b64decode(encoded).decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="https://peluqo-mundos.vercel.app")
    parser.add_argument("--connector", default="http://127.0.0.1:54321")
    args = parser.parse_args()
    device, cloud = read("mochi-education-device.json"), read("cloud-public.json")
    identity = str(uuid4())
    private = ROOT / ".runtime/mochi-family-support-live.json"
    report = {"passed": False, "data": "fictional_demonstration", "signalId": identity,
              "syntheticInput": True, "childAudioRecorded": False, "audioPlayed": False,
              "transcriptPublished": False, "externalNotificationsSent": False,
              "cleanupRequired": True}
    private.write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        with httpx.Client(timeout=150, follow_redirects=False) as client:
            family = login(client, read("qa-integral-family.json"), cloud)
            teacher = login(client, read("teacher-demo.json"), cloud)
            before = snapshot(client, args.web, family)
            learner = next(item for item in before["learners"] if item["id"] == device["learnerId"])
            assert learner["name"] == "Explorador de Peluqo", "Use only the known fictional demonstration learner"
            settings = next(item for item in before["settings"] if item["learnerId"] == learner["id"])
            assert settings.get("familySupportAlertsEnabled") is True, "Enable consent in the demo family's actual settings first"
            headers = {"Authorization": "Bearer " + device["token"], "X-Mochi-Turn-ID": identity}
            offer = client.post(args.connector + "/v1/education/turn", headers=headers,
                content=pcm(ROOT / ".runtime/education-support-peer.wav"))
            report.update(offerHttp=offer.status_code, offerKind=offer.headers.get("x-mochi-education-reply"))
            assert offer.status_code == 200 and offer.headers.get("x-mochi-education-reply") == "support", "Synthetic disclosure was not recognized"
            assert "¿Quieres" in caption(offer), "The child must be offered a choice before any notice"
            intermediate = snapshot(client, args.web, family)
            assert all(item["id"] != identity for item in intermediate.get("careAlerts", [])), "Notice was created before child confirmation"
            headers["X-Mochi-Turn-ID"] = str(uuid4())
            confirmation = client.post(args.connector + "/v1/education/turn", headers=headers,
                content=pcm(ROOT / ".runtime/education-support-confirm.wav"))
            report.update(confirmationHttp=confirmation.status_code, confirmationKind=confirmation.headers.get("x-mochi-education-reply"))
            assert confirmation.status_code == 200 and "He dejado un aviso" in caption(confirmation), "The minimal notice was not confirmed"
            after = snapshot(client, args.web, family)
            alert = next(item for item in after.get("careAlerts", []) if item["id"] == identity)
            assert alert["category"] == "possible_peer_bullying" and alert["status"] == "pending_review"
            assert set(alert) <= {"id", "learnerId", "category", "createdAt", "status", "reviewedAt"}, "Unexpected personal content in family notice"
            teacher_view = snapshot(client, args.web, teacher)
            assert "careAlerts" not in teacher_view and identity not in json.dumps(teacher_view), "Teacher received private accompaniment data"
            report.update(passed=True, offeredBeforeConfirmation=True, minimalFamilyNoticeVisible=True,
                          teacherCannotSeeNotice=True, rawConversationShared=False,
                          source="real_asr_tts_and_authenticated_school_api")
    finally:
        private.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    public = {key: value for key, value in report.items() if key != "signalId"}
    (ROOT / "docs/mediciones/20261105-mochi-family-support-live.json").write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(public))


if __name__ == "__main__":
    main()
