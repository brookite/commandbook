"""Tests for command assembly from a template."""

from __future__ import annotations

from commandbook.commands.builder import RenderSpec, build_command, referenced_names


def test_simple_substitution():
    result = build_command("echo ${msg}", {"msg": "hi"})
    assert result == "echo hi"


def test_value_is_quoted():
    result = build_command("echo ${msg}", {"msg": "a b"})
    assert result == "echo 'a b'"


def test_optional_segment_present():
    template = "docker build -t ${tag}[[ -f ${dockerfile}]] ${context}"
    result = build_command(template, {"tag": "img", "dockerfile": "Dockerfile", "context": "."})
    assert result == "docker build -t img -f Dockerfile ."


def test_optional_segment_absent():
    template = "docker build -t ${tag}[[ -f ${dockerfile}]] ${context}"
    result = build_command(template, {"tag": "img", "context": "."})
    assert result == "docker build -t img ."


def test_checkbox_gates_segment():
    template = "git log[[ --oneline${short}]]"
    assert build_command(template, {"short": True}) == "git log --oneline"
    assert build_command(template, {"short": False}) == "git log"


def test_cwd_bare_and_braced():
    result = build_command("cd $cwd && ls ${cwd}", {}, cwd="/tmp/work")
    assert result == "cd /tmp/work && ls /tmp/work"


def test_empty_optional_value_drops_segment():
    template = "cmd[[ --name ${name}]]"
    assert build_command(template, {"name": ""}) == "cmd"
    assert build_command(template, {"name": "x"}) == "cmd --name x"


def test_bare_value_is_not_escaped():
    specs = {"x": RenderSpec(escape=False)}
    assert build_command("run ${x}", {"x": "a b --flag"}, specs=specs) == "run a b --flag"


def test_quote_style_double():
    specs = {"x": RenderSpec(quote_style="double")}
    assert build_command("echo ${x}", {"x": "a b"}, specs=specs) == 'echo "a b"'


def test_quote_style_backtick():
    specs = {"x": RenderSpec(quote_style="backtick")}
    assert build_command("echo ${x}", {"x": "a b"}, specs=specs) == "echo a` b"
    assert build_command("echo ${x}", {"x": "$v"}, specs=specs) == "echo `$v"


def test_strip_quotes_removes_one_layer():
    specs = {"x": RenderSpec(strip_quotes=True)}
    assert build_command("echo ${x}", {"x": '"hello"'}, specs=specs) == "echo hello"
    # Combined with bare: no escaping, quotes stripped.
    bare = {"x": RenderSpec(escape=False, strip_quotes=True)}
    assert build_command("echo ${x}", {"x": "'hi'"}, specs=bare) == "echo hi"


def test_custom_quote_as_is_used():
    def quote_as(style: str, value: str) -> str:
        return f"<{style}:{value}>"

    result = build_command("run ${x}", {"x": "v"}, quote_as=quote_as)
    assert result == "run <auto:v>"


def test_referenced_names():
    assert referenced_names("a ${one} b ${two} ${one}") == ["one", "two"]
    assert referenced_names("no placeholders") == []
