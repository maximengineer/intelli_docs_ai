from statistics import mean


def average(values: list[float]) -> float:
    return mean(values) if values else 0.0
