#!/usr/bin/env bash
# Deploys a pointer descriptor into the HOI4 mod folder so the launcher can find
# the in-game companion mod that lives in this repo. Idempotent.
#
# Usage:  bash scripts/deploy-mod.sh
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
mod_src="$repo_root/mod"

# Resolve the user's Documents folder (Windows Git Bash: $USERPROFILE/Documents).
docs="${USERPROFILE:-$HOME}/Documents"
mod_dir="$docs/Paradox Interactive/Hearts of Iron IV/mod"
mkdir -p "$mod_dir"

# HOI4 needs a Windows-style path with forward slashes (e.g. C:/Users/...),
# NOT a Git Bash / MSYS path (/c/Users/...). Convert it.
if command -v cygpath >/dev/null 2>&1; then
  mod_src_fwd="$(cygpath -m "$mod_src")"
else
  mod_src_fwd="$(echo "$mod_src" | sed -E 's#^/([a-zA-Z])/#\U\1:/#; s#\\#/#g')"
fi
target="$mod_dir/factory_optimizer_companion.mod"

cat > "$target" <<EOF
name="Factory Optimizer Companion"
path="$mod_src_fwd"
supported_version="1.19.*"
tags={
	"Utilities"
}
EOF

echo "Wrote $target"
echo "Points at: $mod_src_fwd"
echo "Enable 'Factory Optimizer Companion' in the HOI4 launcher mod list."
