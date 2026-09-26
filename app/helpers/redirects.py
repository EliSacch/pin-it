from urllib.parse import urlparse


def safe_redirect_target(candidate):
    if not isinstance(candidate, str) or not candidate:
        return None
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return None
    return candidate


def submitted_redirect_target(request):
    return safe_redirect_target(request.form.get("next") or request.args.get("next"))
