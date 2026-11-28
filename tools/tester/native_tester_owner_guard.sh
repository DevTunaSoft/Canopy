#!/usr/bin/env bash
# Read-only single-owner probe for org.freedesktop.Notifications in the guest.
# Invoked from tools/tester/native_tester_guest.sh; no name is requested and no
# daemon is started. Process-name checks use pgrep -x so the caller's SSH
# command line cannot self-match a forbidden token.
set -uo pipefail
OUT="${1:-/dev/stdout}"
exec > "$OUT" 2>&1
pass=1
say(){ printf '%s\n' "$*"; }
req(){ if [ "$2" != "$3" ]; then say "OWNER_GUARD_FAIL $1 got=[$2] want=[$3]"; pass=0; else say "OWNER_GUARD_OK $1=$2"; fi; }

say "UTC=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
BUS=org.freedesktop.DBus
OBJ=/org/freedesktop/DBus
NAME=org.freedesktop.Notifications
RAW=$(timeout 8 gdbus call --session --dest "$BUS" --object-path "$OBJ" \
      --method org.freedesktop.DBus.GetNameOwner "$NAME" 2>&1)
say "GET_NAME_OWNER_RAW=$RAW"
OWNER=$(printf '%s' "$RAW" | sed -n "s/^('\(.*\)',)$/\1/p")
if printf '%s' "$OWNER" | grep -Eq '^:[0-9]+(\.[0-9]+)?$'; then
  say "NOTIFICATION_OWNER=$OWNER"
else
  say "OWNER_GUARD_FAIL owner_not_unique owner=[$OWNER]"; pass=0
fi

PIDRAW=$(timeout 8 gdbus call --session --dest "$BUS" --object-path "$OBJ" \
         --method org.freedesktop.DBus.GetConnectionUnixProcessID "$OWNER" 2>&1)
# gdbus returns "(uint32 5422,)": tr -cd would also capture the digits in
# "uint32" and produce a bogus PID such as 325422.
PID=$(printf '%s' "$PIDRAW" | sed -n 's/.*uint32 \([0-9][0-9]*\).*/\1/p')
COMM=$([ -n "$PID" ] && [ -r "/proc/$PID/comm" ] && cat "/proc/$PID/comm" || echo UNKNOWN)
say "OWNER_PID=$PID OWNER_COMM=$COMM"
if [ -n "$PID" ] && [ "$PID" -gt 0 ] 2>/dev/null; then say "OWNER_PID_VALID=yes"; else say "OWNER_GUARD_FAIL owner_pid_invalid"; pass=0; fi
req owner_comm "$COMM" plasmashell

FOREIGN=""
for p in dunst mako notify-osd notification-daemon xfce4-notifyd; do
  match=$(pgrep -x "$p" 2>/dev/null | tr '\n' ' ')
  [ -n "$match" ] && FOREIGN="$FOREIGN $p:$match"
done
FOREIGN=$(printf '%s' "$FOREIGN" | tr -d ' ')
say "FOREIGN_NOTIFICATION_DAEMONS=[$FOREIGN]"
req foreign_daemon_count "$(printf '%s' "$FOREIGN" | wc -w)" 0

CANOPY=""
for p in canopy-notifications canopy-notifier canopy-notification-daemon; do
  match=$(pgrep -x "$p" 2>/dev/null | tr '\n' ' ')
  [ -n "$match" ] && CANOPY="$CANOPY $p:$match"
done
CANOPY=$(printf '%s' "$CANOPY" | tr -d ' ')
say "CANOPY_NOTIFICATION_DAEMONS=[$CANOPY]"
req canopy_daemon_count "$(printf '%s' "$CANOPY" | wc -w)" 0

SERVICE_ALL=$( { grep -rl -- "$NAME" /usr/share/dbus-1/services "$HOME/.local/share/dbus-1/services" 2>/dev/null || true; } | sort -u | grep -v '^$' || true)
UPSTREAM_FILE=/usr/share/dbus-1/services/org.kde.plasma.Notifications.service
UPSTREAM_COUNT=$(printf '%s\n' "$SERVICE_ALL" | grep -cxF "$UPSTREAM_FILE" || true)
FOREIGN_FILES=$(printf '%s\n' "$SERVICE_ALL" | grep -vxF "$UPSTREAM_FILE" | grep -v '^$' || true)
say "SERVICE_FILES_ALL=[$(printf '%s' "$SERVICE_ALL" | tr '\n' ' ')]"
say "UPSTREAM_SERVICE_FILE=$UPSTREAM_FILE count=$UPSTREAM_COUNT"
say "FOREIGN_SERVICE_FILE_COUNT=$(printf '%s\n' "$FOREIGN_FILES" | grep -c . || true)"
req upstream_service_files "$UPSTREAM_COUNT" 1
req foreign_activatable_duplicates "$(printf '%s\n' "$FOREIGN_FILES" | grep -c . || true)" 0

NAMES=$(timeout 8 gdbus call --session --dest "$BUS" --object-path "$OBJ" \
        --method org.freedesktop.DBus.ListNames 2>/dev/null | grep -o "$NAME" | wc -l)
say "NAMES_LIST_OCCURRENCES=$NAMES"
req bus_name_occurrences "$NAMES" 1

if [ "$pass" -eq 1 ]; then
  say "OWNER_GUARD_PASS guarded_names=6 upstream_service_files=$UPSTREAM_COUNT foreign_service_files=0"
  exit 0
fi
say "OWNER_GUARD_FAIL"
exit 1
