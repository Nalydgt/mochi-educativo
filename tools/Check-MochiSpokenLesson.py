"""Verify a fictional spoken lesson through the real PC speaker and Mochi mic.

Prepare a new demonstration with at least two questions, first answer six, and
adult settings voiceEnabled=true, textFirst=false. Put Mochi near the PC speaker.
The test opens the introduction, listens for completed nonzero speaker DMA,
holds the on-screen voice button, plays synthetic speech, and requires exactly
one locally accepted answer followed by the next automatic spoken question.
It never submits a numeric answer through USB or an HTTP API.

Use only synthetic input in a quiet demonstration without private conversation.
The physical device temporarily captures sound and uses its normal configured
voice service. This tool saves no microphone audio, transcript, child identifier,
configuration, or token. Its default numeric report stays under private .runtime.
I2S evidence does not measure physical speaker loudness or first acoustic sound.

Examples (run only when the USB port is free):
  python tools/Check-MochiSpokenLesson.py --generate-fixture
  python tools/Check-MochiSpokenLesson.py --input .runtime/answer.wav --expected-choice 6
  python tools/Check-MochiSpokenLesson.py --resume-current-question --expected-choice 6
"""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import wave

from mochi_device import Device, voice_timings

ROOT = Path(__file__).resolve().parents[1]
CANCEL_FILE = None
LESSON_FIELDS = {
    "ready", "open", "completed", "queued", "synced", "question", "count",
    "attempts", "hints", "a", "b", "simulation", "intro", "voice_mode",
}
AV_FIELDS = {"tap", "active", "mean", "level", "dma_age_ms", "sequence", "speaking"}
RESPONSE_FIELDS = {
    "http", "bytes", "rate", "overflow", "streamed", "played", "first_audio_ms",
    "first_pcm_ms", "first_i2s_ms", "upload_ms", "headers_ms", "i2s_tick_ms",
}


class CheckFailure(RuntimeError):
    """A controlled diagnostic reason, safe to save without raw board output."""


def require(condition, reason):
    if not condition:
        raise CheckFailure(reason)


def fields(line, allowed):
    return {key: int(value) for key, value in re.findall(r"(\w+)=(-?\d+)", line)
            if key in allowed}


def remaining(deadline, cap=4):
    require(CANCEL_FILE is None or not CANCEL_FILE.exists(), "verification_cancelled_by_file")
    seconds = deadline - time.monotonic()
    require(seconds > 0, "verification_deadline_expired")
    return min(seconds, cap)


def pause(seconds, deadline):
    time.sleep(min(seconds, remaining(deadline)))


def query(board, command, prefix, allowed, deadline):
    return fields(board.command(command, prefix, timeout=remaining(deadline)), allowed)


def lesson(board, deadline):
    return query(board, "@lesson-status", "@mochi_lesson ", LESSON_FIELDS, deadline)


def status(board, deadline):
    return query(board, "@status", "@mochi_status ", {"configured", "wifi", "busy", "reason"}, deadline)


def av(board, deadline):
    return query(board, "@mochi-av", "@mochi_av ", AV_FIELDS, deadline)


def save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class ObservedDevice(Device):
    """Add safe failure/capture metadata while retaining Device's USB protocol."""
    def __init__(self, port):
        super().__init__(port)
        self.failures = []
        self.captures = []
        self.education_replies = []
        self.education_answers = []

    def __enter__(self):
        super().__enter__()
        self.port = ObservedPort(self.port, self.failures, self.captures,
                                 self.education_replies, self.education_answers)
        return self


class ObservedPort:
    def __init__(self, port, failures, captures, education_replies, education_answers):
        self.wrapped = port
        self.failures = failures
        self.captures = captures
        self.education_replies = education_replies
        self.education_answers = education_answers
        self.pending = bytearray()

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def read(self, count):
        data = self.wrapped.read(count)
        self.pending.extend(data)
        while b"\n" in self.pending:
            line, _, tail = self.pending.partition(b"\n")
            self.pending[:] = tail
            decoded = line.decode("utf-8", "replace")
            if "Voice failed: " in decoded:
                row = fields(decoded, {"http"})
                for key in ("stage", "result", "detail"):
                    match = re.search(r"\b" + key + r"=([A-Za-z0-9_\-]{1,64})\b", decoded)
                    if match:
                        row[key] = match.group(1)
                self.failures.append(row)
            if "Voice capture: " in decoded:
                self.captures.append(fields(decoded, {"samples", "bytes", "peak", "rms", "context", "step",
                                                      "cancelled", "blocked"}))
            if "Education reply: " in decoded:
                row = fields(decoded, {"context", "answer", "step"})
                kind = re.search(r"\bkind=([A-Za-z0-9_\-]{1,64})\b", decoded)
                if kind:
                    row["kind"] = kind.group(1)
                self.education_replies.append(row)
            if "Education answer: " in decoded:
                self.education_answers.append(fields(decoded, {"matched", "applied", "cancelled"}))
        if len(self.pending) > 16384:
            self.pending.clear()
        return data


def generate_fixture(path, expected_choice):
    """Local Windows SAPI fixture; no NAS, browser, secret, or microphone access."""
    require(os.name == "nt", "windows_required_for_sapi_fixture")
    require(expected_choice == 6, "sapi_fixture_is_six_use_input_for_other_answers")
    require(not path.exists(), "fixture_exists_use_input_to_preserve_it")
    path.parent.mkdir(parents=True, exist_ok=True)
    script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voices = @($synth.GetInstalledVoices() | Where-Object {
        $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'es'
    })
    if ($voices.Count -eq 0) { throw 'No Spanish SAPI voice is installed' }
    $female = @($voices | Where-Object { $_.VoiceInfo.Gender -eq 'Female' })
    $selected = if ($female.Count) { $female[0] } else { $voices[0] }
    $synth.SelectVoice($selected.VoiceInfo.Name)
    $synth.Rate = -1
    $synth.Volume = 100
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        16000,
        [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToWaveFile($env:MOCHI_QA_SYNTHETIC_PATH, $format)
    $synth.Speak('Seis.')
    $synth.SetOutputToNull()
} finally { $synth.Dispose() }
"""
    environment = os.environ.copy()
    environment["MOCHI_QA_SYNTHETIC_PATH"] = str(path)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment, capture_output=True, timeout=30, check=False,
    )
    require(result.returncode == 0 and path.is_file(), "spanish_sapi_fixture_generation_failed")


def inspect_fixture(path):
    require(path.is_file(), "synthetic_input_missing_use_input_or_generate_fixture")
    with wave.open(str(path), "rb") as wav:
        require((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) ==
                (1, 2, 16000, "NONE"), "input_requires_mono_16khz_pcm16_wav")
        frames = wav.getnframes()
        # Manual capture is bounded to eight seconds on the board. Leave room
        # for the deliberate long press, microphone setup, and final silence.
        require(3200 <= frames <= 80000, "synthetic_input_must_last_0_2_to_5_seconds")
        pcm = wav.readframes(frames)
    require(len(pcm) == frames * 2, "synthetic_input_truncated")
    samples = array("h", pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    require(peak > 100 and rms > 20, "synthetic_input_is_silent")
    return {
        "duration_seconds": frames / 16000,
        "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "sample_rate": 16000, "channels": 1, "sample_width_bytes": 2,
        "peak": peak, "rms": round(rms, 2),
    }


class Pointer:
    def __init__(self, board):
        self.board = board
        self.position = (233, 96)
        self.held = False
        self.created = False

    def send(self, x, y, pressed, deadline):
        # Mark the intent before the write so cleanup also releases a press
        # whose USB acknowledgement was lost.
        self.position = (x, y)
        if pressed:
            self.held = True
        self.created = True
        reply = self.board.command(f"@ui-pointer {x} {y} {int(pressed)}",
                                   "@mochi_ui_pointer ", timeout=remaining(deadline))
        require(reply == "@mochi_ui_pointer ok", "ui_pointer_rejected")
        self.held = bool(pressed)

    def tap(self, x, y, deadline):
        self.send(x, y, True, deadline)
        pause(.15, deadline)
        self.send(x, y, False, deadline)
        pause(.15, deadline)

    def cleanup(self):
        if not self.created:
            return True
        try:
            if self.held:
                x, y = self.position
                self.board.command(f"@ui-pointer {x} {y} 0", "@mochi_ui_pointer ", timeout=3)
                self.held = False
                # Let LVGL consume RELEASED before deleting its diagnostic
                # input device, including on a failed or interrupted test.
                time.sleep(.15)
            reply = self.board.command("@ui-pointer -1 -1 0", "@mochi_ui_pointer ", timeout=3)
            return reply == "@mochi_ui_pointer ok"
        except Exception:
            return False


def response_events(board, first):
    """Only bounded numeric fields survive; never persist detail or raw logs."""
    found = []
    for index in range(first, len(board.events)):
        line = board.events[index]
        if line.startswith("Voice response: "):
            row = fields(line, RESPONSE_FIELDS)
            result = re.search(r"\bresult=(ESP_[A-Z0-9_]+)\b", line)
            row["result"] = result.group(1) if result else "unknown"
            row["result_ok"] = row["result"] == "ESP_OK"
            found.append((index, row))
    return found


def nonzero_dma(row, baseline_sequence):
    return (row.get("tap") == 1 and row.get("active") == 1 and row.get("mean", 0) > 0 and
            row.get("dma_age_ms", 10000) <= 250 and row.get("sequence") != baseline_sequence)


def stable_question(current, expected):
    return all(current.get(key) == expected.get(key)
               for key in ("question", "count", "attempts", "hints", "a", "b", "completed"))


def wait_idle(board, deadline):
    stable_since = None
    while True:
        state = status(board, deadline)
        require(state.get("wifi") == 1, "physical_wifi_not_connected")
        if state.get("busy") == 0:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= .4:
                return state
        else:
            stable_since = None
        pause(.1, deadline)


def observe_question(board, expected, baseline, first_event, deadline, report, key):
    """Observe normal automatic TTS, without a diagnostic say/answer command."""
    started = time.monotonic()
    phase_deadline = min(deadline, started + 90)
    observed = {"nonzero_dma_samples": 0, "speaking_state_samples": 0,
                "physical_first_sound_measured": False, "speaker_audio_recorded": False}
    report["observations"][key] = observed
    idle_since = None
    download = None
    while True:
        current_av = av(board, phase_deadline)
        current_status = status(board, phase_deadline)
        current_lesson = lesson(board, phase_deadline)
        require(stable_question(current_lesson, expected), "lesson_changed_during_question")
        require(current_lesson.get("open") == 1 and current_lesson.get("intro") == 0,
                "lesson_closed_or_returned_to_intro")
        if nonzero_dma(current_av, baseline.get("sequence")):
            observed["nonzero_dma_samples"] += 1
            observed["speaking_state_samples"] += int(current_av.get("speaking") == 1)
            observed.setdefault("first_observed_dma_seconds", round(time.monotonic() - started, 3))
            observed["last_sequence"] = current_av["sequence"]
        for _, row in response_events(board, first_event):
            observed["download"] = row
            require(row.get("result_ok") and row.get("http") == 200 and
                    row.get("overflow") == 0 and row.get("rate") == 16000 and row.get("bytes", 0) > 0,
                    "automatic_question_download_failed")
            download = row
        if current_status.get("busy") == 0 and observed["nonzero_dma_samples"] and download:
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since >= .4:
                observed.update(download=download, busy_returned_idle=True,
                                elapsed_seconds=round(time.monotonic() - started, 3),
                                output_evidence="completed_nonzero_i2s_dma")
                return current_av
        else:
            idle_since = None
        pause(.08, phase_deadline)


def play_answer(board, pointer, winsound, path, fixture, before, deadline, report, output):
    board.events.clear()
    first_failure = len(board.failures)
    first_capture = len(board.captures)
    first_education_reply = len(board.education_replies)
    first_education_answer = len(board.education_answers)
    baseline = av(board, deadline)
    held_since = time.monotonic()
    pointer.send(233, 96, True, deadline)
    intent_deadline = min(deadline, held_since + 6)
    while True:
        current = lesson(board, intent_deadline)
        state = status(board, intent_deadline)
        require(stable_question(current, before), "lesson_changed_before_synthetic_input")
        if current.get("voice_mode") == 1 and state.get("busy") == 1:
            break
        pause(.1, intent_deadline)
    while time.monotonic() - held_since < 1.1:
        pause(.05, deadline)
    report["observations"]["microphone_intent"] = {
        "deliberate_long_press": True, "lesson_voice_mode": 1, "audio_owner_busy": 1,
        "recording_flag_read_directly": False, "pointer_x": 233, "pointer_y": 96,
    }
    save(output, report)
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    played_since = time.monotonic()
    try:
        while time.monotonic() - played_since < fixture["duration_seconds"] + .35:
            state = status(board, deadline)
            current = lesson(board, deadline)
            require(state.get("busy") == 1 and current.get("voice_mode") == 1,
                    "voice_owner_stopped_during_synthetic_input")
            require(stable_question(current, before), "lesson_changed_while_voice_button_held")
            pause(.08, deadline)
    finally:
        winsound.PlaySound(None, 0)
        pointer.send(233, 96, False, deadline)
    report["observations"]["microphone_intent"]["hold_seconds"] = round(time.monotonic() - held_since, 3)
    report["observations"]["microphone_intent"]["pc_synthetic_playback_completed"] = True

    report["observations"]["spoken_reply"] = observed = {
        "nonzero_dma_samples": 0, "physical_first_sound_measured": False,
        "speaker_audio_recorded": False,
    }
    turn_event = None
    turn_index = None
    phase_deadline = min(deadline, time.monotonic() + 90)
    idle_since = None
    last_checkpoint = 0
    while True:
        current_av = av(board, phase_deadline)
        current = lesson(board, phase_deadline)
        current_status = status(board, phase_deadline)
        observed["last_status"] = current_status
        observed["last_lesson"] = current
        observed["failures"] = board.failures[first_failure:]
        observed["capture_metrics"] = board.captures[first_capture:]
        observed["education_reply_metadata"] = board.education_replies[first_education_reply:]
        observed["education_answer_metadata"] = board.education_answers[first_education_answer:]
        if nonzero_dma(current_av, baseline.get("sequence")):
            observed["nonzero_dma_samples"] += 1
        if turn_event is None:
            events = response_events(board, 0)
            if events:
                turn_index, turn_event = events[0]
                require(turn_event.get("result_ok") and turn_event.get("http") == 200 and
                        turn_event.get("overflow") == 0 and turn_event.get("bytes", 0) > 0,
                        "spoken_answer_voice_request_failed")
                if turn_event.get("streamed") == 1:
                    require(turn_event.get("played") == turn_event.get("bytes"),
                            "streamed_reply_pcm_incomplete")
                observed.update(response=turn_event, **voice_timings(turn_event))
                save(output, report)
        if current.get("attempts", 0) > before["attempts"]:
            require(current["attempts"] == before["attempts"] + 1 and
                    current.get("question") == before["question"] + 1 and
                    current.get("hints") == before["hints"] and
                    current.get("count") == before["count"] and current.get("open") == 1,
                    "spoken_answer_did_not_advance_exactly_one_matching_question")
            require(turn_event is not None and observed["nonzero_dma_samples"] > 0,
                    "local_advance_without_observed_complete_spoken_reply")
            # Runtime applies the contextual numeric answer only after its reply
            # drain. For buffered fallback the download log's played count is
            # zero; the subsequent state transition is the completion evidence.
            observed.update(local_context_accepted=True, reply_drained_before_local_apply=True,
                            output_evidence="nonzero_i2s_dma_and_post_drain_local_answer")
            report["observations"]["after_spoken_answer"] = current
            return current, current_av, turn_index + 1
        require(stable_question(current, before), "unrelated_lesson_state_changed_during_voice_reply")
        if current_status.get("busy") == 0:
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since >= 1:
                require(False, "spoken_turn_finished_without_matching_local_answer")
        else:
            idle_since = None
        if time.monotonic() - last_checkpoint >= 1:
            save(output, report)
            last_checkpoint = time.monotonic()
        pause(.08, phase_deadline)


def run(args):
    global CANCEL_FILE
    CANCEL_FILE = args.cancel_file
    started = time.monotonic()
    deadline = started + args.timeout
    board = None
    pointer = None
    winsound = None
    report = {
        "passed": False, "stage": "input", "data": "fictional_demonstration",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic_pc_speaker_input": True, "expected_choice": args.expected_choice,
        "microphone_audio_saved_on_pc": False, "transcripts_saved": False,
        "private_configuration_read": False, "student_identifier_read": False,
        "numeric_answer_injected": False, "firmware_flashed": False,
        "settings_modified": False, "physical_first_sound_measured": False,
        "resume_existing": args.resume_current_question,
        "prior_progress_attributed_to_test": False,
        "observations": {},
    }
    failure = None
    try:
        require(os.name == "nt", "windows_required_for_real_pc_speaker_playback")
        import winsound as windows_sound
        winsound = windows_sound
        path = args.input.resolve()
        if args.generate_fixture:
            generate_fixture(path, args.expected_choice)
        report["synthetic_fixture"] = inspect_fixture(path)
        save(args.output, report)
        report["stage"] = "preflight"
        board = ObservedDevice(args.port)
        board.__enter__()
        pointer = Pointer(board)
        firmware = board.command("@firmware", "@mochi_firmware ", timeout=remaining(deadline))
        version = re.search(r"\bversion=([A-Za-z0-9_.+\-]{1,80})\b", firmware)
        report["firmware_version"] = version.group(1) if version else "unknown"
        mode = query(board, "@peluqo-status", "@peluqo ",
                     {"active", "paired", "mic", "busy", "options", "menu", "volume"}, deadline)
        require(mode.get("active") == mode.get("paired") == mode.get("mic") == 1 and
                mode.get("options") == 0 and mode.get("menu", 0) == 0,
                "paired_education_with_enabled_microphone_and_closed_menus_required")
        require("volume" not in mode or mode["volume"] > 0,
                "spoken_playback_verification_requires_unmuted_device_volume")
        policy = query(board, "@education-policy", "@mochi_education_policy ",
                       {"ready", "allowed", "voice", "captions", "text_first"}, deadline)
        require(policy.get("ready") == policy.get("allowed") == policy.get("voice") == 1,
                "adult_policy_does_not_allow_spoken_practice_now")
        require(policy.get("text_first") == 0, "spoken_flow_requires_text_first_false")
        report["observations"]["policy"] = policy
        report["observations"]["initial_idle"] = wait_idle(board, deadline)
        before = lesson(board, deadline)
        require(before.get("ready") == 1 and before.get("completed") == 0 and before.get("simulation") == 0 and
                before.get("count", 0) > before.get("question", 0) >= 1,
                "unfinished_fictional_lesson_with_another_question_after_this_one_required")
        if args.resume_current_question:
            require(before.get("open") == 1 and before.get("intro") == 0 and before.get("voice_mode") == 0,
                    "resume_requires_current_question_open_and_idle")
        else:
            require(before.get("open") == 0 and before.get("question") == 1 and
                    before.get("attempts") == 0 and before.get("hints") == 0,
                    "new_closed_fictional_lesson_required_or_use_explicit_resume")
        require(before.get("a", 0) > 0 and before.get("b", 0) > 0 and
                before["a"] * before["b"] == args.expected_choice,
                "synthetic_expected_choice_does_not_match_current_downloaded_question")
        report["observations"]["downloaded"] = before
        baseline = av(board, deadline)
        first_event = len(board.events)

        report["stage"] = "introduction"
        if args.resume_current_question:
            # The Misión button opens the instructions without answering or
            # resetting anything. Continue rearms the normal question cue.
            pointer.tap(111, 96, deadline)
        else:
            pointer.tap(233, 352, deadline)
        opened = lesson(board, deadline)
        require(opened.get("open") == 1 and opened.get("intro") == 1,
                "lesson_introduction_was_not_opened")
        require(stable_question(opened, before), "opening_instructions_changed_existing_progress")
        report["observations"]["introduction"] = opened
        # This point is an answer button during an activity. Never tap it
        # unless the immediately checked state really is the introduction.
        pointer.tap(233, 367, deadline)
        continued = lesson(board, deadline)
        require(continued.get("open") == 1 and continued.get("intro") == 0 and
                stable_question(continued, before), "introduction_did_not_preserve_and_continue_question")
        before = continued
        report["observations"]["before_spoken_answer"] = before
        report["stage"] = "first_automatic_question"
        observe_question(board, before, baseline, first_event, deadline, report, "first_question")
        save(args.output, report)

        report["stage"] = "synthetic_spoken_answer"
        after, baseline, first_event = play_answer(board, pointer, winsound, path,
                                                  report["synthetic_fixture"], before, deadline, report, args.output)
        save(args.output, report)
        report["stage"] = "next_automatic_question"
        require(after.get("completed") == 0, "second_question_required_for_fluent_spoken_flow_check")
        observe_question(board, after, baseline, first_event, deadline, report, "next_question")
        report.update(passed=True, stage="complete", next_question_without_extra_tap=True,
                      actual_acoustic_input_proven_by_contextual_local_advance=True)
    except Exception as error:
        failure = error
        report["error"] = {
            "type": type(error).__name__,
            "reason": str(error) if isinstance(error, CheckFailure) else "verification_io_or_runtime_failure",
        }
    finally:
        if winsound is not None:
            try:
                winsound.PlaySound(None, 0)
            except Exception:
                pass
        if pointer is not None:
            report["diagnostic_pointer_released"] = pointer.cleanup()
            if not report["diagnostic_pointer_released"]:
                report["passed"] = False
                report.setdefault("error", {"type": "CleanupFailure", "reason": "pointer_cleanup_not_acknowledged"})
        if board is not None:
            report["serial_voice_failures"] = board.failures
            report["serial_capture_metrics"] = board.captures
            report["serial_education_replies"] = board.education_replies
            report["serial_education_answers"] = board.education_answers
            try:
                board.__exit__(None, None, None)
            except Exception:
                report["passed"] = False
                report.setdefault("error", {"type": "CleanupFailure", "reason": "usb_close_failed"})
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save(args.output, report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["passed"] and failure is None else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--input", type=Path, default=ROOT / ".runtime/education-answer-six.wav",
                        help="Existing synthetic mono 16 kHz PCM16 WAV, 0.2 to 5 seconds")
    parser.add_argument("--expected-choice", type=int, default=6)
    parser.add_argument("--generate-fixture", action="store_true",
                        help="Create the missing input with a local Spanish SAPI voice saying 'Seis.'")
    parser.add_argument("--resume-current-question", action="store_true",
                        help="Preserve existing progress, reopen Misión, and test the current question")
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/mochi-spoken-lesson.json")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--cancel-file", type=Path,
                        help="Stop cleanly if this previously absent file is created during verification")
    args = parser.parse_args()
    if not 1 <= args.expected_choice <= 144:
        parser.error("--expected-choice must be between 1 and 144")
    if not 30 <= args.timeout <= 600:
        parser.error("--timeout must be between 30 and 600 seconds")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
