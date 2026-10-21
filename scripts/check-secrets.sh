#!/bin/sh
set -eu

cd "$(git rev-parse --show-toplevel)"

if command -v gitleaks >/dev/null 2>&1; then
    scanner="$(command -v gitleaks)"
elif [ -x /opt/homebrew/bin/gitleaks ]; then
    scanner=/opt/homebrew/bin/gitleaks
elif [ -x /usr/local/bin/gitleaks ]; then
    scanner=/usr/local/bin/gitleaks
else
    echo "Gitleaks is required; the operation is blocked." >&2
    exit 1
fi

mode="${1:-history}"

case "$mode" in
    staged)
        set -- git --pre-commit --staged
        ;;
    history)
        git rev-parse --verify HEAD >/dev/null

        if [ "$(git rev-parse --is-shallow-repository)" = true ]; then
            echo "Full history is required; shallow checkout rejected." >&2
            exit 1
        fi

        set -- git "--log-opts=--all --no-ext-diff --no-textconv"
        ;;
    *)
        echo "Usage: check-secrets.sh staged|history" >&2
        exit 2
        ;;
esac

scan_log="$(mktemp)"
trap 'rm -f "$scan_log"' EXIT
trap 'exit 1' HUP INT TERM

scan_status=0

"$scanner" "$@" \
    --redact=100 \
    --exit-code=1 \
    --no-banner \
    --no-color \
    . >"$scan_log" 2>&1 || scan_status=$?

cat "$scan_log"

# Reject explicit scanner errors and incomplete scans.
if grep -Eiq \
    '(^|[[:space:]])(ERR|FTL)([[:space:]]|$)|partial scan' \
    "$scan_log"; then
    exit 1
fi

# A history scan of this committed project must scan commits.
if [ "$mode" = history ] &&
   grep -Eq '(^|[[:space:]])0 commits? scanned' "$scan_log"; then
    echo "No commits were scanned; the operation is blocked." >&2
    exit 1
fi

exit "$scan_status"