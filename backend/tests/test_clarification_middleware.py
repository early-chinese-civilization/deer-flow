from deerflow.agents.middlewares.clarification_middleware import ClarificationMiddleware


def _format_message(args: dict) -> str:
    return ClarificationMiddleware()._format_clarification_message(args)


def test_clarification_options_accept_json_string_list() -> None:
    message = _format_message(
        {
            "question": "Choose one",
            "clarification_type": "approach_choice",
            "options": '["Option A", "Option B"]',
        }
    )

    assert "  1. Option A" in message
    assert "  2. Option B" in message
    assert "  1. [" not in message
    assert '  2. "' not in message


def test_clarification_options_do_not_split_plain_string() -> None:
    message = _format_message(
        {
            "question": "Choose one",
            "clarification_type": "approach_choice",
            "options": "Option A",
        }
    )

    assert "  1. Option A" in message
    assert "  2. p" not in message


def test_clarification_options_keep_json_scalar_string_as_single_option() -> None:
    message = _format_message(
        {
            "question": "Choose one",
            "clarification_type": "approach_choice",
            "options": "1",
        }
    )

    assert "  1. 1" in message


def test_clarification_options_keep_list_format() -> None:
    message = _format_message(
        {
            "question": "Choose one",
            "clarification_type": "approach_choice",
            "options": ["Option A", "Option B"],
        }
    )

    assert "  1. Option A" in message
    assert "  2. Option B" in message
