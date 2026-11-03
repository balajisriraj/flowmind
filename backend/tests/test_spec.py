from flowmind.hub import ToolInfo
from flowmind.spec import Arg, Condition, Step, Trigger, Workflow, coerce, holds, render, validate

CTX = {
    "trigger": {"file": "inbox/a.txt"},
    "steps": {"x": {"amount": 7200.0, "vendor": 'Acme "Ltd"', "rows": [{"a": 1}]}},
}
TOOLS = {
    "notify.post_message": ToolInfo(
        "notify",
        "post_message",
        "",
        {
            "properties": {"channel": {"type": "string"}, "text": {"type": "string"}, "level": {"type": "string"}},
            "required": ["channel", "text"],
        },
        False,
    ),
    "sheets.append_row": ToolInfo(
        "sheets",
        "append_row",
        "",
        {"properties": {"path": {"type": "string"}, "row": {"type": "object"}}, "required": ["path", "row"]},
        False,
    ),
}


def tool_step(id_, tool, args, when=None):
    return Step(
        id=id_,
        title=id_,
        kind="tool",
        tool=tool,
        args=[Arg(name=k, value=v) for k, v in args.items()],
        instruction="",
        input="",
        fields=[],
        when=when,
    )


def test_templates_keep_types_and_interpolate():
    assert render("{{steps.x.amount}}", CTX) == 7200.0
    assert render("Paid {{steps.x.amount}} for {{trigger.file}}", CTX) == "Paid 7200 for inbox/a.txt"
    assert render("{{steps.x.rows.0.a}}", CTX) == 1


def test_object_arguments_escape_values_safely():
    row = coerce('{"vendor": "{{steps.x.vendor}}", "amount": "{{steps.x.amount}}"}', {"type": "object"}, CTX)
    assert row == {"vendor": 'Acme "Ltd"', "amount": "7200"}
    assert coerce("3", {"type": "integer"}, CTX) == 3


def test_conditions():
    assert holds(Condition(left="{{steps.x.amount}}", op="gt", right="5000"), CTX)
    assert not holds(Condition(left="{{steps.x.amount}}", op="lt", right="5,000"), CTX)
    assert holds(Condition(left="{{steps.x.vendor}}", op="contains", right="acme"), CTX)
    assert not holds(Condition(left="{{steps.missing.x}}", op="exists", right=""), CTX)


def test_validation_catches_designer_mistakes():
    wf = Workflow(
        name="w",
        summary="s",
        trigger=Trigger(type="file", every_minutes=0, folder="", pattern=""),
        steps=[
            tool_step("a", "notify.post_message", {"channel": "#x", "message": "{{steps.later.v}}"}),
            tool_step("b", "nope.tool", {}),
            tool_step(
                "c",
                "sheets.append_row",
                {"path": "l.csv", "row": "{}"},
                Condition(left="{{trigger.mood}}", op="exists", right=""),
            ),
        ],
    )
    problems = "\n".join(validate(wf, TOOLS))
    assert "file trigger needs a folder" in problems
    assert "needs argument 'text'" in problems and "has no argument 'message'" in problems
    assert "refers to step 'later'" in problems
    assert "unknown tool 'nope.tool'" in problems
    assert "the trigger only provides" in problems
