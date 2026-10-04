#!/usr/bin/env bash
# i18n helper — run from project root
#
#   ./i18n.sh extract   — collect new strings from templates/python into messages.pot
#   ./i18n.sh update    — merge new strings into each language .po file
#   ./i18n.sh compile   — compile .po files to .mo (what the app reads)
#   ./i18n.sh init      — initialize .po for a language (see LANG arg below)
#   ./i18n.sh all       — extract + update + compile

set -e
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true

LANGS="en ar fr de es ur hi tr"

case "${1:-all}" in
  extract)
    echo "→ Extracting strings..."
    pybabel extract -F babel.cfg -o app/translations/messages.pot app/
    ;;
  update)
    echo "→ Updating each language .po..."
    for lang in $LANGS; do
      if [ -f "app/translations/$lang/LC_MESSAGES/messages.po" ]; then
        pybabel update -i app/translations/messages.pot -d app/translations -l "$lang" --no-fuzzy-matching
        echo "  ✓ $lang"
      fi
    done
    ;;
  compile)
    echo "→ Compiling .po → .mo..."
    pybabel compile -d app/translations
    echo "  ✓ done"
    ;;
  init)
    if [ -z "${2:-}" ]; then
      echo "Usage: ./i18n.sh init <lang>"
      exit 1
    fi
    pybabel init -i app/translations/messages.pot -d app/translations -l "$2"
    ;;
  all)
    $0 extract
    $0 update
    $0 compile
    ;;
  *)
    echo "Unknown command: $1"
    echo "Usage: $0 {extract|update|compile|init|all}"
    exit 1
    ;;
esac

echo "✅ done"
