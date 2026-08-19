import os
import re
from pathlib import Path

# Minimal version shim. ALL OTHER METADATA (description, urls, classifiers,
# python_requires, author, maintainer, license, etc.) lives in pyproject.toml
# — duplicating them here caused PyPI to reject uploads with HTTP 400
# because the wheel ended up with both a deprecated `Home-page:` field
# (from this file's old `url=`) and a `Project-URL: Homepage` field (from
# pyproject.toml) pointing at different URLs.
#
# This file is kept solely so:
#   1. CI_COMMIT_TAG (GitLab CI) can still override the version, and
#   2. Older pip / setuptools versions that expect a setup.py find one.
#
# The publish.yml workflow stamps the version from the git tag, so this
# fallback is rarely exercised in practice — but harmless to keep.
def _get_version():
    if os.getenv('CI_COMMIT_TAG'):
        return os.getenv('CI_COMMIT_TAG').lstrip('v')
    pyproject = Path(__file__).resolve().parent / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding='utf-8')
        m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if m:
            return m.group(1)
    return '0.0.0'

# Importing setup lazily so older environments without setuptools fail
# with a clearer error than the bare `import setuptools` would surface.
try:
    from setuptools import setup
except ImportError:
    import sys
    sys.exit("setuptools is required to build this package")

setup(version=_get_version())
