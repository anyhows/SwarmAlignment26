#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --quiet --no-project --with-requirements "$package_dir/requirements.lock" \
  python "$package_dir/run.py" "$@"
