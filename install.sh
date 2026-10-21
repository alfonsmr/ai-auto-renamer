#!/usr/bin/env zsh
# ============================================================================
# AI Auto Renamer — macOS Finder Quick Action ("Smart Rename") Installer
# ============================================================================
# Usage:
#   ./install.sh                      # Set up ./config/ (if missing) & install Quick Action
#   ./install.sh --no-service-install # Only generate ./config/ and ./Smart Rename.workflow locally
#   ./install.sh --config-dir=PATH    # Use a custom config directory path
# ============================================================================
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
CONFIG_DIR="${SCRIPT_DIR}/config"
EXAMPLE_DIR="${SCRIPT_DIR}/config.example"
WORKFLOW_TEMPLATE_DIR="${SCRIPT_DIR}/workflow.template"
LOCAL_WORKFLOW_DIR="${SCRIPT_DIR}/Smart Rename.workflow"
SERVICES_DIR="${HOME}/Library/Services"
INSTALL_SERVICE=true

usage() {
  cat <<EOF
Usage: ./install.sh [OPTIONS]

Options:
  --no-service-install   Generate ./config/ and ./Smart Rename.workflow locally without
                         installing into ~/Library/Services
  --config-dir=PATH      Path to configuration directory (default: ./config)
  -h, --help             Show this help message and exit
EOF
}

for arg in "$@"; do
  case "$arg" in
    --no-service-install)
      INSTALL_SERVICE=false
      ;;
    --config-dir=*)
      CONFIG_DIR="${arg#*=}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown option '$arg'" >&2
      usage >&2
      exit 1
      ;;
  esac
done

chmod +x "${SCRIPT_DIR}/smart_rename.py"

# 1. Create ./config/ and copy starter templates ONLY if they don't already exist
mkdir -p "${CONFIG_DIR}"

copy_if_missing() {
  local src="$1"
  local dst="$2"
  local label="$3"
  if [[ -f "${dst}" ]]; then
    echo "• Kept existing ${label}: ${dst}"
  else
    cp "${src}" "${dst}"
    echo "• Created default ${label}: ${dst}"
  fi
}

echo "===================================================================="
echo "  AI Auto Renamer — Installing Configuration & Quick Action"
echo "===================================================================="

copy_if_missing "${EXAMPLE_DIR}/settings.example.json" "${CONFIG_DIR}/settings.json" "settings.json"
copy_if_missing "${EXAMPLE_DIR}/tags.example.json" "${CONFIG_DIR}/tags.json" "tags.json"
copy_if_missing "${EXAMPLE_DIR}/system_prompt.example.md" "${CONFIG_DIR}/system_prompt.md" "system_prompt.md"

# 2. Generate "./Smart Rename.workflow" from "./workflow.template"
rm -rf "${LOCAL_WORKFLOW_DIR}"
mkdir -p "${LOCAL_WORKFLOW_DIR}/Contents"

cp "${WORKFLOW_TEMPLATE_DIR}/Contents/Info.plist" "${LOCAL_WORKFLOW_DIR}/Contents/Info.plist"
/usr/bin/python3 -c '
import html, pathlib, sys
tpl_path = pathlib.Path(sys.argv[1])
out_path = pathlib.Path(sys.argv[2])
script_path = sys.argv[3]
escaped_path = html.escape(script_path, quote=True)
content = tpl_path.read_text(encoding="utf-8").replace("{{SCRIPT_PATH}}", escaped_path)
out_path.write_text(content, encoding="utf-8")
' "${WORKFLOW_TEMPLATE_DIR}/Contents/document.wflow.template" \
  "${LOCAL_WORKFLOW_DIR}/Contents/document.wflow" \
  "${SCRIPT_DIR}/smart_rename.py"

echo "• Built workflow bundle: ${LOCAL_WORKFLOW_DIR}"

# 3. Install into ~/Library/Services/Smart Rename.workflow
if [[ "${INSTALL_SERVICE}" == "true" ]]; then
  mkdir -p "${SERVICES_DIR}"
  rm -rf "${SERVICES_DIR}/Smart Rename.workflow"

  cp -R "${LOCAL_WORKFLOW_DIR}" "${SERVICES_DIR}/Smart Rename.workflow"
  echo "• Installed Finder Quick Action: ${SERVICES_DIR}/Smart Rename.workflow"

  if [[ -x "/System/Library/CoreServices/pbs" ]]; then
    /System/Library/CoreServices/pbs -update >/dev/null 2>&1 || true
  fi

  /usr/bin/python3 "${SCRIPT_DIR}/smart_rename.py" --sync-tags --config-dir "${CONFIG_DIR}" >/dev/null 2>&1 || true
  echo "• Synchronized Finder Tag Database & sidebar tags from: ${CONFIG_DIR}/tags.json"
fi

echo ""
echo "===================================================================="
echo "  Installation Complete!"
echo "===================================================================="
echo "IMPORTANT — First-Time Finder Step (Required by macOS):"
echo "  New Quick Actions are not enabled by default on macOS."
echo "  1. Right-click any file in Finder → Quick Actions → Customize..."
echo "  2. Enable (check) 'Smart Rename' in the Extensions list."
echo ""
echo "Try it now:"
echo "  • In Finder : Right-click any supported document → Quick Actions → Smart Rename"
echo "  • In Terminal: /usr/bin/python3 smart_rename.py --dry-run examples/sample_*"
