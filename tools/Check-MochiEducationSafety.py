"""Run the fictional protection walkthrough. Does not send notifications."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "services/peluqo_education/lesson_dialogue.py"
spec = importlib.util.spec_from_file_location("mochi_lesson_dialogue", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.safeguarding_demo()
assert result["simulation"]
assert not result["automaticNotificationSent"]
assert not result["fullConversationShared"]
assert result["humanReview"] == "pending_in_demonstration"
output = ROOT / "docs/mediciones/20261105-proteccion-simulada.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"passed": True, "simulation": True, "liveNotification": False,
                  "output": str(output)}, ensure_ascii=False))
