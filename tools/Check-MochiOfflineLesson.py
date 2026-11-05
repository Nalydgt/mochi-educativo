"""Exercise a fictional lesson on the real board with its Wi-Fi radio stopped.

The serial lesson commands call the same state transitions as the touch buttons.
No microphone capture, private configuration, token or student identifier is read.
This script changes volatile radio state and restarts the board once. It does not
flash firmware, erase progress or modify saved Wi-Fi networks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

import serial

from mochi_device import Device

ROOT = Path(__file__).resolve().parents[1]
LESSON_FIELDS = {
    "ready", "open", "completed", "queued", "synced", "question", "count",
    "attempts", "hints", "a", "b", "simulation",
}
VPN_FIELDS = {"configured", "worker", "phase", "state", "ready", "peers", "direct", "error"}


def fields(line, allowed):
    return {
        key: int(value)
        for key, value in re.findall(r"(\w+)=(-?\d+)", line)
        if key in allowed
    }


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def remaining(deadline, cap=5):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("The bounded board verification deadline expired")
    return min(seconds, cap)


def close(board):
    if board is not None:
        try:
            board.__exit__(None, None, None)
        except (OSError, serial.SerialException):
            pass


def connect(port, deadline):
    while time.monotonic() < deadline:
        board = Device(port)
        try:
            board.__enter__()
            board.command("@firmware", "@mochi_firmware ", timeout=remaining(deadline, 3))
            return board
        except (OSError, serial.SerialException, TimeoutError):
            close(board)
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    raise TimeoutError("The board did not reconnect within the bounded retry window")


def lesson(board, deadline):
    line = board.command("@lesson-status", "@mochi_lesson ", timeout=remaining(deadline))
    return fields(line, LESSON_FIELDS)


def status(board, deadline):
    line = board.command("@status", "@mochi_status ", timeout=remaining(deadline))
    return fields(line, {"configured", "wifi", "busy", "reason"})


def action(board, command, prefix, deadline):
    line = board.command(command, prefix, timeout=remaining(deadline))
    require("accepted=1" in line, "The board rejected a lesson action")


def radio(board, enable, deadline):
    value = "on" if enable else "off"
    retries = 0
    idle_waits = 0
    retryable = {
        "ESP_ERR_INVALID_STATE", "ESP_ERR_WIFI_NOT_INIT", "ESP_ERR_WIFI_NOT_STARTED",
        "ESP_ERR_WIFI_NOT_STOPPED", "ESP_ERR_WIFI_STATE",
    }
    while True:
        current = status(board, deadline)
        if current.get("busy") != 0:
            idle_waits += 1
            time.sleep(min(0.25, remaining(deadline)))
            continue
        line = board.command("@wifi-radio " + value, "@mochi_wifi_radio ", timeout=remaining(deadline))
        match = re.search(r"\bresult=(ESP_[A-Z0-9_]+)\b", line)
        result = match.group(1) if match else "ESP_UNKNOWN_RESULT"
        retries += 1
        if result == "ESP_OK":
            break
        require(result in retryable, "The board returned an unexpected physical radio result")
        time.sleep(min(0.25, remaining(deadline)))
    if not enable:
        while time.monotonic() < deadline:
            current = status(board, deadline)
            if current.get("wifi") == 0:
                return {**current, "radio_result": result, "command_attempts": retries,
                        "idle_waits": idle_waits}
            time.sleep(0.15)
        raise TimeoutError("The physical Wi-Fi connection did not stop")
    return {**status(board, deadline), "radio_result": result, "command_attempts": retries,
            "idle_waits": idle_waits}


def save(output, report):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def restore_report(path, report):
    """Validate the completed first phase, then retain its exact original file."""
    raw = path.read_bytes()
    prior = json.loads(raw)
    observations = prior.get("observations", {})
    partial = observations.get("persisted_before_restart", {})
    restored = observations.get("restored_after_restart", {})
    downloaded = observations.get("downloaded", {})
    wrong = observations.get("incorrect_answer_offline", {})
    require(prior.get("data") == "fictional_demonstration" and
            prior.get("physical_wifi_radio_stopped") is True and
            prior.get("simulation_used") is False and
            prior.get("restart_persistence_verified") is True and
            observations.get("radio_stopped", {}).get("wifi") == 0,
            "Resume requires recorded physical radio-off and restart-persistence evidence")
    require(downloaded.get("ready") == 1 and downloaded.get("count", 0) >= 2 and
            downloaded.get("question") == 1 and downloaded.get("attempts") == 0 and
            downloaded.get("hints") == 0 and downloaded.get("simulation") == 0 and
            wrong.get("question") == 1 and wrong.get("attempts") == 1 and
            wrong.get("completed") == 0 and partial.get("question") == 2 and
            partial.get("attempts") == 2 and partial.get("hints") == 1 and
            partial.get("completed") == 0 and partial.get("queued") == 0 and
            partial.get("synced") == 0,
            "The first report does not contain the expected incorrect answer, hint and partial lesson")
    stable = ("ready", "question", "count", "attempts", "hints", "completed", "queued", "synced", "a", "b", "simulation")
    for key in stable:
        require(restored.get(key) == partial.get(key), "The prior restart did not preserve the lesson")
    archive = ROOT / ".runtime" / ("mochi-offline-first-attempt-" + hashlib.sha256(raw).hexdigest()[:16] + ".json")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        archive.write_bytes(raw)
    # Copy only known numeric observations; do not propagate arbitrary text
    # from a supplied report into a public measurements artifact.
    for key in ("downloaded", "before_radio_stop", "radio_stopped", "incorrect_answer_offline",
                "persisted_before_restart", "restored_after_restart"):
        report["observations"][key] = {
            name: value for name, value in observations[key].items()
            if name in LESSON_FIELDS | {"configured", "wifi", "busy", "reason"} and isinstance(value, int)
        }
    report.update(resumed=True, physical_wifi_radio_stopped=True,
                  restart_persistence_verified=True,
                  prior_attempt_archive=archive.name,
                  prior_attempt_elapsed_seconds=prior.get("elapsed_seconds"))
    return {key: partial[key] for key in stable}


def run(args):
    started = time.monotonic()
    deadline = started + args.timeout
    board = None
    report = {
        "passed": False,
        "resumed": False,
        "data": "fictional_demonstration",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "physical_wifi_radio_stopped": False,
        "simulation_used": False,
        "microphone_audio_recorded": False,
        "private_configuration_read": False,
        "firmware_flashed": False,
        "saved_networks_modified": False,
        "touch_buttons_physically_pressed": False,
        "same_lesson_state_transitions_as_touch_ui": True,
        "observations": {},
    }
    observations = report["observations"]
    failure = None
    try:
        board = connect(args.port, deadline)
        if args.resume_from is not None:
            expected = restore_report(args.resume_from, report)
            current = lesson(board, deadline)
            for key, value in expected.items():
                require(current.get(key) == value,
                        "The current board lesson differs from the preserved first-attempt counters")
            observations["resumed_current"] = current
            save(args.output, report)
        else:
            # A new assignment avoids mixing this deliberately wrong answer with
            # any existing exercise. Waiting never resets or overwrites local work.
            while True:
                current = lesson(board, deadline)
                require(current.get("simulation") == 0, "Disable the simulated offline flag before this physical test")
                if current.get("ready") == 1 and current.get("count", 0) >= 2:
                    require(current.get("completed") == 0 and current.get("question") == 1 and
                            current.get("attempts") == 0 and current.get("hints") == 0,
                            "A fresh fictional lesson is required; existing progress was preserved")
                    observations["downloaded"] = current
                    break
                time.sleep(min(0.5, remaining(deadline)))
            before_radio = status(board, deadline)
            require(before_radio.get("wifi") == 1 and before_radio.get("busy") == 0,
                    "The board must be connected and idle before the physical test")
            observations["before_radio_stop"] = before_radio
            observations["radio_stopped"] = radio(board, False, deadline)
            report["physical_wifi_radio_stopped"] = True
            save(args.output, report)

            action(board, "@lesson-start", "@mochi_lesson_start ", deadline)
            original = lesson(board, deadline)
            require(original.get("a", 0) > 0 and original.get("b", 0) > 0,
                    "The downloaded exercise must contain positive factors")
            action(board, "@lesson-answer 0", "@mochi_lesson_answer ", deadline)
            wrong = lesson(board, deadline)
            require(wrong.get("question") == original.get("question") and
                    wrong.get("attempts") == original.get("attempts", 0) + 1 and
                    wrong.get("completed") == 0,
                    "An incorrect answer must preserve the exercise and record one attempt")
            observations["incorrect_answer_offline"] = wrong
            action(board, "@lesson-hint", "@mochi_lesson_hint ", deadline)
            hinted = lesson(board, deadline)
            require(hinted.get("hints") == wrong.get("hints", 0) + 1,
                    "The offline hint was not persisted")
            product = original["a"] * original["b"]
            action(board, f"@lesson-answer {product}", "@mochi_lesson_answer ", deadline)
            partial = lesson(board, deadline)
            require(partial.get("question") == original["question"] + 1 and
                    partial.get("attempts") == wrong["attempts"] + 1 and
                    partial.get("completed") == 0,
                    "The correct offline answer did not advance to the next exercise")
            action(board, "@lesson-rest", "@mochi_lesson_rest ", deadline)
            partial = lesson(board, deadline)
            require(partial.get("open") == 0, "The rest action did not close the exercise")
            require(status(board, deadline).get("wifi") == 0,
                    "The physical radio unexpectedly reconnected during the offline activity")
            observations["persisted_before_restart"] = partial
            save(args.output, report)

            reply = board.command("@restart", "@mochi_restart ", timeout=remaining(deadline))
            require("queued" in reply, "The board rejected the controlled restart")
            close(board)
            board = None
            # Avoid claiming success from a command served by the old boot. Native
            # USB normally disappears; the bounded delay also covers fast reconnects.
            time.sleep(min(1.2, remaining(deadline)))
            board = connect(args.port, min(deadline, time.monotonic() + 35))
            restored = lesson(board, deadline)
            for key in ("ready", "question", "count", "attempts", "hints", "completed", "queued", "synced"):
                require(restored.get(key) == partial.get(key),
                        "Persisted lesson counters changed across the board restart")
            require(restored.get("simulation") == 0, "The physical test must not use the simulation flag")
            observations["restored_after_restart"] = restored
            report["restart_persistence_verified"] = True
        # Restart restores normal Wi-Fi initialization. Stop the real radio
        # again before completing any remaining exercises.
        observations["radio_stopped_after_restart"] = radio(board, False, deadline)
        action(board, "@lesson-start", "@mochi_lesson_start ", deadline)
        while True:
            current = lesson(board, deadline)
            if current.get("completed") == 1:
                break
            require(current.get("a", 0) > 0 and current.get("b", 0) > 0,
                    "The remaining offline exercise has invalid factors")
            action(board, f"@lesson-answer {current['a'] * current['b']}",
                   "@mochi_lesson_answer ", deadline)
        offline_complete = lesson(board, deadline)
        require(offline_complete.get("completed") == 1 and offline_complete.get("queued") == 1 and
                offline_complete.get("synced") == 0 and offline_complete.get("simulation") == 0,
                "The completed offline result must remain queued and unsynchronized")
        require(status(board, deadline).get("wifi") == 0,
                "Offline completion was not observed with the physical radio stopped")
        observations["completed_without_wifi"] = offline_complete
        report["offline_exercise_and_queue_verified"] = True
        report["remote_database_checked"] = False
        save(args.output, report)

        radio(board, True, deadline)
        sync_deadline = min(deadline, time.monotonic() + 90)
        while True:
            current = lesson(board, sync_deadline)
            connection = status(board, sync_deadline)
            vpn = fields(board.command("@vpn", "@mochi_vpn ", timeout=remaining(sync_deadline)), VPN_FIELDS)
            if (current.get("queued") == 0 and current.get("synced") == 1 and
                    current.get("completed") == 1 and connection.get("wifi") == 1 and vpn.get("ready") == 1):
                observations["after_synchronization"] = current
                observations["wifi_restored"] = connection
                observations["vpn_restored"] = vpn
                break
            time.sleep(min(0.5, remaining(sync_deadline)))
        report["server_acknowledgment_observed_on_device"] = True
        report["passed"] = True
    except Exception as error:
        # Exception messages from serial libraries may include arbitrary device
        # output. Retain the exception class and the controlled stage only.
        report["failure_type"] = type(error).__name__
        report["failure_after_observations"] = len(observations)
        failure = error
    finally:
        restore_deadline = time.monotonic() + 18
        try:
            if board is None or not board.port.is_open:
                close(board)
                board = connect(args.port, min(restore_deadline, time.monotonic() + 8))
            restored_radio = radio(board, True, restore_deadline)
            report["radio_restore_command_accepted"] = restored_radio["radio_result"] == "ESP_OK"
            report["radio_restore_result"] = restored_radio["radio_result"]
            while time.monotonic() < restore_deadline:
                final_status = status(board, restore_deadline)
                if final_status.get("wifi") == 1:
                    report["radio_restored_connected"] = True
                    break
                time.sleep(0.3)
            else:
                report["radio_restored_connected"] = False
        except Exception as restore_error:
            report["radio_restored_connected"] = False
            report["radio_restore_failure_type"] = type(restore_error).__name__
        close(board)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save(args.output, report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    if failure is not None:
        raise SystemExit(1)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/mediciones/20261105-mochi-offline.json")
    parser.add_argument("--timeout", type=float, default=240,
                        help="Overall verification timeout in seconds; sync waits at most 90 seconds")
    parser.add_argument("--resume-from", type=Path,
                        help="Continue the same partial lesson after a report verified restart persistence")
    args = parser.parse_args()
    if args.timeout < 30:
        parser.error("--timeout must be at least 30 seconds")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
