"""A9 (axChat CONTROLLER_SPEC §6.2): the README opens with a single-prompt example, and that example runs."""
import contextlib
import io
import re
from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


def test_the_first_example_is_a_single_prompt_and_it_runs():
    first = re.search(r"```python\n(.*?)```", README, re.S).group(1)
    assert "run(" in first and "start_agent" not in first
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(first, {})
    assert out.getvalue().strip() == "True STUB: Say hello in five words."


def test_the_single_prompt_example_comes_before_the_agent_one():
    assert README.index("from ai_factory import Config, run") < README.index("start_agent(")
