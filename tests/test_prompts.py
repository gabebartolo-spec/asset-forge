import io
import json
import subprocess

import pytest

from asset_forge import prompts
from asset_forge.prompts import PromptGenError, llm
from asset_forge.prompts.templates import MAX_PROMPT_CHARS, SUFFIX


def _fake(text):
    return lambda system, idea, asset_type: text


def test_humanoid_front_has_view_words(monkeypatch):
    monkeypatch.setattr(llm, "generate", _fake("A tall knight in blue plate armour."))
    out = prompts.expand("knight", "humanoid")
    assert out.startswith("A tall knight in blue plate armour, ")
    assert "T-pose" in out and "plain white background" in out and "front view" in out


def test_animal_is_side_on(monkeypatch):
    monkeypatch.setattr(llm, "generate", _fake("A small round robin."))
    assert "side-on" in prompts.expand("robin", "animal")


def test_sprite_back_is_an_explicit_turned_view(monkeypatch):
    monkeypatch.setattr(llm, "generate", _fake("A fox with a flame tail."))
    out = prompts.expand("fire fox", "sprite", "back")
    assert "from directly behind" in out and "face hidden" in out


def test_back_only_for_sprites():
    with pytest.raises(PromptGenError, match="sprites"):
        prompts.expand("brute", "monster", "back")


def test_empty_idea_and_bad_type():
    with pytest.raises(PromptGenError, match="few words"):
        prompts.expand("   ", "monster")
    with pytest.raises(PromptGenError, match="Unknown type"):
        prompts.expand("x", "vehicle")


def test_output_trimmed_to_one_line_and_capped(monkeypatch):
    long = "- \"" + "word " * 200 + "\"\nsecond line ignored"
    monkeypatch.setattr(llm, "generate", _fake(long))
    out = prompts.expand("brute", "monster")
    assert "\n" not in out and "second line" not in out
    assert len(out) <= MAX_PROMPT_CHARS
    assert not out.startswith(("-", '"'))


def test_empty_model_answer_uses_the_idea(monkeypatch):
    monkeypatch.setattr(llm, "generate", _fake("   "))
    assert prompts.expand("robin", "animal").startswith("robin, ")


def test_missing_model_names_the_fix(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_MODELS_DIR", str(tmp_path))
    with pytest.raises(PromptGenError, match="not installed"):
        prompts.expand("robin", "animal")


def test_missing_model_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_MODELS_DIR", str(tmp_path))
    out = prompts.expand("robin", "animal", allow_fallback=True)
    assert out == f"robin, {SUFFIX[('animal', 'front')]}"
    assert out == prompts.fallback("robin", "animal")


def test_deterministic(monkeypatch):
    monkeypatch.setattr(llm, "generate", _fake("A grey brute with six arms."))
    first = prompts.expand("six-armed brute", "monster")
    assert first == prompts.expand("six-armed brute", "monster")


class FakeProc:
    def __init__(self, lines, code=None):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self.code = code

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return self.code


def _install(monkeypatch, tmp_path, proc):
    py = tmp_path / "envs" / "promptgen" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_text("")
    monkeypatch.setenv("FORGE_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(llm, "_proc", None)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: proc)


def test_worker_failure_is_plain_words(monkeypatch, tmp_path):
    llm._errlog.seek(0)
    llm._errlog.truncate()
    llm._errlog.write("boom\nCUDA out of memory")
    _install(monkeypatch, tmp_path, FakeProc([], code=1))
    with pytest.raises(PromptGenError, match="CUDA out of memory"):
        prompts.expand("robin", "animal")


def test_worker_answer_is_parsed_and_reused(monkeypatch, tmp_path):
    ready = json.dumps({"ready": True, "load_s": 3})
    reply = json.dumps({"text": "A robin.", "load_s": 3, "gen_s": 1, "vram_mb": 3})
    proc = FakeProc([ready, reply, reply])
    _install(monkeypatch, tmp_path, proc)
    assert prompts.expand("robin", "animal").startswith("A robin, ")
    assert prompts.expand("robin", "animal").startswith("A robin, ")
    assert proc.stdin.getvalue().count("\n") == 2  # one resident worker, two jobs


def test_messages_carry_system_and_example():
    msgs = llm.build_messages("SYS", "robin", "animal")
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[-1] == {"role": "user", "content": "robin"}


def test_templates_never_state_a_limb_count():
    import re

    from asset_forge.prompts.templates import SUFFIX, SYSTEM

    count = re.compile(
        r"(one|two|three|four|five|six|seven|eight|\d+)[\w\s-]{0,12}"
        r"(legs?|arms?|fours|wings?|heads?|eyes?)",
        re.I,
    )
    for text in [*SUFFIX.values(), *SYSTEM.values()]:
        assert not count.search(text), text
    assert "all fours" not in " ".join(SUFFIX.values())
