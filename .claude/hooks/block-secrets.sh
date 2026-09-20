#!/usr/bin/env bash
# Blocks edits that introduce obvious secrets. Reads tool input JSON on stdin.
input=$(cat)
content=$(echo "$input" | python3 -c 'import sys,json; d=json.load(sys.stdin); ti=d.get("tool_input",{}); print(ti.get("content") or ti.get("new_string") or "")' 2>/dev/null)
if echo "$content" | grep -Eq 'AKIA[0-9A-Z]{16}|dapi[0-9a-f]{32}|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----|aws_secret_access_key\s*='; then
  echo "Blocked: edit appears to contain a credential. Use Secrets Manager." >&2
  exit 2
fi
exit 0
