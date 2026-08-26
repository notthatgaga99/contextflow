from app.context.compiler import ContextCompiler
from app.llm import tokens
from tests.conftest import make_task


def _task():
    t = make_task("A", "jwt", "debug jwt auth", ["401 unresolved"], ["jwt"])
    t.anchor.decisions = ["use RS256"]
    t.anchor.constraints = ["do not change API contract"]
    t.anchor.entities = ["JWT middleware"]
    return t


def test_split_has_both_token_counts():
    pkg = ContextCompiler().build(_task(), "split")
    assert pkg.decision_tokens > 0 and pkg.answer_tokens > 0
    assert pkg.answer_tokens >= pkg.decision_tokens


def test_merged_zero_decision_tokens():
    pkg = ContextCompiler().build(_task(), "merged")
    assert pkg.decision_tokens == 0 and pkg.answer_tokens > 0


def test_token_counts_match_helper():
    pkg = ContextCompiler().build(_task(), "split")
    d, a = tokens.count_package(pkg)
    assert (pkg.decision_tokens, pkg.answer_tokens) == (d, a)
