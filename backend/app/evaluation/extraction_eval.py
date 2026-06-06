from app.documents.schemas import ExtractedFields


def _values_match(actual: object, expected: object) -> bool:
    if actual is None or expected is None:
        return actual is expected
    try:
        return float(actual) == float(expected)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(actual).strip().lower() == str(expected).strip().lower()


def extraction_field_accuracy(actual: ExtractedFields, expected: dict[str, object]) -> float:
    if not expected:
        return 0.0
    matched = sum(
        1
        for key, expected_value in expected.items()
        if _values_match(getattr(actual, key, None), expected_value)
    )
    return matched / len(expected)
