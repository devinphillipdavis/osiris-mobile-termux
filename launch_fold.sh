#!/data/data/com.termux/files/usr/bin/bash
#
# launch_fold.sh — the fold-aware OSIRIS lab.
#
#   Unfolded (>= 100 cols): one window, split side-by-side.
#       pane 0 (left)  unified REPL
#       pane 1 (right) live telemetry / AuditChain / genome monitor
#   Folded / cover display (< 100 cols): the monitor is broken out to its own window,
#       because a 44-column pane split two ways is unreadable. Prefix+T toggles to it.
#
# The layout follows the hinge: a `client-resized` hook re-runs --relayout, so folding
# and unfolding the device rearranges the lab live without restarting anything.
#
# Usage:
#   ./launch_fold.sh                  create or attach
#   ./launch_fold.sh --relayout       re-lay out for the current client width
#   ./launch_fold.sh --toggle         show/hide the monitor
#   ./launch_fold.sh --kill           end the session
#   ./launch_fold.sh --threshold 90   change the fold cutoff (columns)
#   ./launch_fold.sh --status         print layout state and exit (no attach)
#
# Copyright (c) 2026 Devin Phillip Davis / Agile Defense Systems LLC
set -euo pipefail

SESSION="${OSIRIS_TMUX_SESSION:-osiris}"
THRESHOLD="${OSIRIS_FOLD_THRESHOLD:-100}"
WINDOW="lab"
MONITOR="monitor"
ACTION="launch"

HERE="$(cd "$(dirname "$0")" && pwd)"
CONF="$HERE/config/tmux.fold.conf"
SELF="$HERE/$(basename "$0")"

while [ $# -gt 0 ]; do
  case "$1" in
    --relayout)  ACTION="relayout"; shift ;;
    --toggle)    ACTION="toggle"; shift ;;
    --kill)      ACTION="kill"; shift ;;
    --status)    ACTION="status"; shift ;;
    --session)   SESSION="${2:?--session needs a name}"; shift 2 ;;
    --threshold) THRESHOLD="${2:?--threshold needs a column count}"; shift 2 ;;
    -h|--help)   sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)           echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

command -v tmux >/dev/null 2>&1 || { echo "tmux not installed: pkg install tmux" >&2; exit 1; }

# ── Environment ───────────────────────────────────────────────────────────────
[ -f "$HOME/.osiris/env.sh" ] && . "$HOME/.osiris/env.sh"
OSIRIS_HOME="${OSIRIS_HOME:-$HOME/.osiris}"
VENV_PY="${OSIRIS_VENV:-$OSIRIS_HOME/venv}/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$(command -v python3 || command -v python)"
[ -n "$VENV_PY" ] || { echo "no python interpreter found" >&2; exit 1; }

# Pane commands. Each is wrapped so that if the module is missing the pane drops to an
# interactive shell with the reason on screen, rather than closing and collapsing the split.
REPL_CMD="cd '$HERE' && '$VENV_PY' -m osiris_mobile.repl || { echo; echo 'REPL exited — falling back to a shell.'; exec bash; }"
MON_CMD="cd '$HERE' && '$VENV_PY' -m osiris_mobile.telemetry.tail --interval 2 || { echo; echo 'monitor exited — falling back to a shell.'; exec bash; }"

has_session() { tmux has-session -t "=$SESSION" 2>/dev/null; }
client_width() {
  local w
  w="$(tmux display-message -p -t "=$SESSION" '#{client_width}' 2>/dev/null || true)"
  # No attached client yet (first launch, or --status from outside): ask the terminal.
  if [ -z "$w" ] || [ "$w" = "0" ]; then
    w="$(tput cols 2>/dev/null || echo "${COLUMNS:-80}")"
  fi
  echo "$w"
}
monitor_window_exists() { tmux list-windows -t "=$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx "$MONITOR"; }
lab_pane_count() { tmux list-panes -t "=$SESSION:$WINDOW" -F '#{pane_id}' 2>/dev/null | wc -l | tr -d ' '; }
is_wide() { [ "$(client_width)" -ge "$THRESHOLD" ]; }

# ── Layout primitives ─────────────────────────────────────────────────────────
# Wide: monitor lives as pane 1 of the lab window, to the right of the REPL.
# Narrow: monitor lives in its own window, reachable with prefix+T.
go_wide() {
  if [ "$(lab_pane_count)" -ge 2 ]; then return 0; fi
  if monitor_window_exists; then
    tmux join-pane -h -s "=$SESSION:$MONITOR" -t "=$SESSION:$WINDOW.0"
  else
    tmux split-window -h -t "=$SESSION:$WINDOW.0" "$MON_CMD"
  fi
  # The monitor is a fixed-width readout; give the REPL the larger share.
  tmux resize-pane -t "=$SESSION:$WINDOW.1" -x "40%" 2>/dev/null || true
  tmux select-pane -t "=$SESSION:$WINDOW.0"
  tmux select-pane -t "=$SESSION:$WINDOW.0" -T "REPL" 2>/dev/null || true
  tmux select-pane -t "=$SESSION:$WINDOW.1" -T "telemetry" 2>/dev/null || true
}

go_narrow() {
  if [ "$(lab_pane_count)" -lt 2 ]; then return 0; fi
  tmux break-pane -d -s "=$SESSION:$WINDOW.1" -n "$MONITOR" -t "=$SESSION:"
  tmux select-window -t "=$SESSION:$WINDOW"
}

relayout() {
  has_session || { echo "no session '$SESSION'" >&2; return 1; }
  if is_wide; then go_wide; else go_narrow; fi
}

toggle() {
  has_session || { echo "no session '$SESSION'" >&2; return 1; }
  if [ "$(lab_pane_count)" -ge 2 ]; then
    go_narrow
  elif monitor_window_exists; then
    if is_wide; then go_wide; else tmux select-window -t "=$SESSION:$MONITOR"; fi
  else
    tmux new-window -d -n "$MONITOR" -t "=$SESSION:" "$MON_CMD"
    is_wide && go_wide
  fi
}

print_status() {
  if ! has_session; then echo "session '$SESSION': not running"; return 0; fi
  printf 'session   : %s\n' "$SESSION"
  printf 'width     : %s cols (threshold %s -> %s)\n' \
    "$(client_width)" "$THRESHOLD" "$(is_wide && echo unfolded || echo narrow)"
  printf 'lab panes : %s\n' "$(lab_pane_count)"
  printf 'monitor   : %s\n' "$(monitor_window_exists && echo 'own window' || echo 'joined or absent')"
  tmux list-windows -t "=$SESSION" -F '  window #{window_index} #{window_name} (#{window_panes} panes)'
}

# ── Actions ───────────────────────────────────────────────────────────────────
case "$ACTION" in
  kill)
    has_session && tmux kill-session -t "=$SESSION" && echo "killed '$SESSION'" || echo "no session '$SESSION'"
    exit 0 ;;
  relayout) relayout; exit $? ;;
  toggle)   toggle;   exit $? ;;
  status)   print_status; exit 0 ;;
esac

# ── Launch ────────────────────────────────────────────────────────────────────
if has_session; then
  relayout || true
  if [ -n "${TMUX:-}" ]; then
    exec tmux switch-client -t "=$SESSION"
  fi
  exec tmux attach-session -t "=$SESSION"
fi

mkdir -p "$OSIRIS_HOME"/{logs,telemetry}

WIDTH="$(client_width)"
tmux new-session -d -s "$SESSION" -n "$WINDOW" -x "$WIDTH" -y "$(tput lines 2>/dev/null || echo 40)" "$REPL_CMD"

# Session-scoped options only — the user's global config is not touched.
# Note: set-option rejects the "=" exact-match target prefix that has-session accepts,
# and -q would hide that failure, leaving prefix+R/T silently bound to an empty command.
[ -f "$CONF" ] && tmux source-file -t "$SESSION" "$CONF" 2>/dev/null || true
tmux set-option -t "$SESSION" @osiris_launcher "$SELF"
tmux set-option -t "$SESSION" @osiris_conf "$CONF"

# The monitor starts in its own window; the layout pass below decides where it belongs.
tmux new-window -d -n "$MONITOR" -t "=$SESSION:" "$MON_CMD"

# Follow the hinge. -b so a resize storm during the fold animation cannot block the server.
# No -g: that installs the hook server-wide, so every unrelated tmux session would run
# a relayout against this one on every resize.
tmux set-hook -t "$SESSION" client-resized "run-shell -b '$SELF --relayout --session $SESSION'"

relayout || true

if [ "$WIDTH" -ge "$THRESHOLD" ]; then
  echo "OSIRIS lab: unfolded layout (${WIDTH} cols) — REPL | telemetry"
else
  echo "OSIRIS lab: narrow layout (${WIDTH} cols) — prefix+T for telemetry"
fi

if [ -n "${TMUX:-}" ]; then
  exec tmux switch-client -t "=$SESSION"
fi
exec tmux attach-session -t "=$SESSION"
