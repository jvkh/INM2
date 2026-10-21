"""SQL helpers for matching configured host names and their subdomains."""


def normalized_host_sql(expression: str) -> str:
    """Return a SQL expression that normalizes case, trailing dots, and www."""
    return (
        f"CASE WHEN lower(rtrim({expression}, '.')) LIKE 'www.%' "
        f"THEN substr(lower(rtrim({expression}, '.')), 5) "
        f"ELSE lower(rtrim({expression}, '.')) END"
    )


def known_host_match_sql(expression: str, alias: str = "kh") -> str:
    """Match a host exactly or as a subdomain of a configured known host."""
    normalized = normalized_host_sql(expression)
    suffix = f"'.' || {alias}.name"
    return (
        "EXISTS (SELECT 1 FROM known_host AS "
        f"{alias} WHERE {normalized} = {alias}.name "
        f"OR substr({normalized}, -length({suffix})) = {suffix})"
    )
