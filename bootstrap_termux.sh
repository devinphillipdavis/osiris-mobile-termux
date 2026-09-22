#!/data/data/com.termux/files/usr/bin/bash
#
# bootstrap_termux.sh — OSIRIS Mobile Research Lab deployment for Android/Termux (aarch64).
#
# Brings up the full edge-compute harness on a Pixel Fold (or any arm64 Android device):
#   Termux packages -> venv (system-site numpy) -> source repos -> llama.cpp -> GGUF model
#   -> termux-api sanity -> environment file -> doctor report.
#
# Usage:
#   bash bootstrap_termux.sh [--tier lite|full|quantum] [--model-size 1.5b|3b|none]
#                            [--local-src DIR] [--skip-llama] [--no-upgrade] [--force]
#
# Tiers:
#   lite    (default) numpy only. Runs organism_sim, the LCS/XCS benchmarks, the GRN,
#           chat_bridge and the dnalang front end (lexer/parser/sema/lower/qc_ir).
#           NO qiskit. ~120 MB of wheels, ~5 min.
#   full    lite + scipy/rich/PyYAML from the Termux User Repository, plus the unified
#           `osiris` package (qbyte, LivLM, NCLM). No quantum backends. ~10 min.
#   quantum lite + full + qiskit/qiskit-aer built from source via the Rust toolchain.
#           Expect 30-60 min on a Tensor chip and ~3 GB of scratch. Only needed for the
#           `bridge` repo and `dnalang run --backend aer`.
#
# Idempotent: safe to re-run. Nothing is deleted; existing checkouts are reported, not pulled.
#
# Copyright (c) 2026 Devin Phillip Davis / Agile Defense Systems LLC
# Licensed under the OSIRIS Source-Available Dual License v1.0
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
OSIRIS_HOME="${OSIRIS_HOME:-$HOME/.osiris}"
OSIRIS_SRC="${OSIRIS_SRC:-$HOME/osiris-src}"
VENV="$OSIRIS_HOME/venv"
GH_ORG="${OSIRIS_GH_ORG:-https://github.com/osiris-dnalang}"
LLAMA_REPO="${OSIRIS_LLAMA_REPO:-https://github.com/ggml-org/llama.cpp}"

TIER="lite"
MODEL_SIZE="1.5b"
LOCAL_SRC=""
SKIP_LLAMA=0
DO_UPGRADE=1
FORCE=0

# Repos pulled from the org. dnalang-core and organism_sim are the mobile-critical pair.
REPOS_LITE=("dnalang-core" "organism_sim")
REPOS_FULL=("osiris-cli")

# ── Output helpers ────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_R=$'\033[0m'; C_B=$'\033[1m'; C_G=$'\033[32m'; C_Y=$'\033[33m'; C_E=$'\033[31m'; C_C=$'\033[36m'
else
  C_R=""; C_B=""; C_G=""; C_Y=""; C_E=""; C_C=""
fi
step() { printf '\n%s==> %s%s\n' "$C_B$C_C" "$*" "$C_R"; }
log()  { printf '    %s\n' "$*"; }
ok()   { printf '    %s[ ok ]%s %s\n' "$C_G" "$C_R" "$*"; }
warn() { printf '    %s[warn]%s %s\n' "$C_Y" "$C_R" "$*" >&2; }
die()  { printf '\n%s[fail]%s %s\n' "$C_E" "$C_R" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() { sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

# ── Argument parsing ──────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --tier)        TIER="${2:?--tier needs a value}"; shift 2 ;;
    --model-size)  MODEL_SIZE="${2:?--model-size needs a value}"; shift 2 ;;
    --local-src)   LOCAL_SRC="${2:?--local-src needs a directory}"; shift 2 ;;
    --skip-llama)  SKIP_LLAMA=1; shift ;;
    --no-upgrade)  DO_UPGRADE=0; shift ;;
    --force)       FORCE=1; shift ;;
    -h|--help)     usage ;;
    *)             die "unknown option: $1  (try --help)" ;;
  esac
done

case "$TIER" in lite|full|quantum) ;; *) die "--tier must be lite, full or quantum (got '$TIER')" ;; esac
case "$MODEL_SIZE" in 1.5b|3b|none) ;; *) die "--model-size must be 1.5b, 3b or none (got '$MODEL_SIZE')" ;; esac

# ── 1. Environment sanity ─────────────────────────────────────────────────────
step "1/10  Environment"

IS_TERMUX=0
[ -n "${PREFIX:-}" ] && case "$PREFIX" in *com.termux*) IS_TERMUX=1 ;; esac
if [ "$IS_TERMUX" -eq 0 ]; then
  if [ "$FORCE" -eq 1 ]; then
    warn "not running under Termux; --force given, continuing with pkg steps skipped"
  else
    die "this script targets Termux on Android. Re-run inside Termux, or pass --force to
          dry-run the venv/source/llama.cpp stages on another Linux host."
  fi
fi

ARCH="$(uname -m)"
log "arch          : $ARCH"
log "tier          : $TIER"
log "android       : $(getprop ro.build.version.release 2>/dev/null || echo 'n/a')"
log "device        : $(getprop ro.product.model 2>/dev/null || echo 'n/a')"
case "$ARCH" in
  aarch64|arm64) ok "64-bit ARM" ;;
  *) warn "expected aarch64 (Tensor / Snapdragon); '$ARCH' is untested" ;;
esac

MEM_KB="$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || echo 0)"
if [ "$MEM_KB" -gt 0 ]; then
  log "RAM           : $((MEM_KB / 1024)) MB"
  [ "$MEM_KB" -lt 5500000 ] && warn "under ~6 GB RAM: use --model-size 1.5b and keep agent N <= 2000"
fi

FREE_MB="$(df -Pm "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
log "free in \$HOME : ${FREE_MB:-?} MB"
NEED_MB=2500; [ "$TIER" = "quantum" ] && NEED_MB=6000
if [ -n "${FREE_MB:-}" ] && [ "$FREE_MB" -lt "$NEED_MB" ]; then
  warn "tier '$TIER' wants ~${NEED_MB} MB free; only ${FREE_MB} MB available"
fi

mkdir -p "$OSIRIS_HOME"/{bin,models,logs,results,checkpoints,telemetry} "$OSIRIS_SRC"
ok "state root: $OSIRIS_HOME"

# ── 2. Termux packages ────────────────────────────────────────────────────────
step "2/10  Termux packages"

pkg_install() {   # pkg_install <required|optional> pkg...
  local mode="$1"; shift
  local p
  for p in "$@"; do
    if dpkg -s "$p" >/dev/null 2>&1; then
      log "already installed: $p"
    elif pkg install -y "$p" >/dev/null 2>&1; then
      ok "installed: $p"
    elif [ "$mode" = "required" ]; then
      die "could not install required package '$p'. Run 'pkg install $p' and read the error."
    else
      warn "optional package unavailable: $p"
    fi
  done
}

if [ "$IS_TERMUX" -eq 1 ]; then
  if [ "$DO_UPGRADE" -eq 1 ]; then
    log "pkg update && pkg upgrade (pass --no-upgrade to skip)"
    yes | pkg update  >/dev/null 2>&1 || warn "pkg update reported errors; continuing"
    yes | pkg upgrade >/dev/null 2>&1 || warn "pkg upgrade reported errors; continuing"
  fi

  # Toolchain + runtime. python-pip is split out on recent Termux; tolerate either layout.
  pkg_install required git python clang make cmake tmux binutils pkg-config
  pkg_install optional python-pip libopenblas openssl libandroid-execinfo ndk-sysroot

  # numpy from the Termux repo: a prebuilt wheel-equivalent. Building it from pip on
  # device costs ~25 min and frequently fails on BLAS detection, so this matters.
  pkg_install required python-numpy

  # termux-api is TWO things: this CLI package, and the Termux:API companion APK.
  pkg_install required termux-api

  if [ "$TIER" != "lite" ]; then
    # scipy is not in the main Termux repo; it lives in the Termux User Repository.
    pkg_install optional tur-repo
    if dpkg -s tur-repo >/dev/null 2>&1; then
      yes | pkg update >/dev/null 2>&1 || true
      pkg_install optional python-scipy
    fi
  fi

  if [ "$TIER" = "quantum" ]; then
    warn "quantum tier: qiskit>=1.3 needs a Rust core (rustworkx, qiskit-accelerate)."
    warn "              Expect a 30-60 min compile. Keep the device plugged in."
    pkg_install required rust
    pkg_install optional patchelf
  fi
else
  warn "skipping pkg stage (not Termux)"
fi

# ── 3. termux-api reachability ────────────────────────────────────────────────
step "3/10  termux-api bridge"

API_OK=0
if have termux-battery-status; then
  if BATT="$(timeout 10 termux-battery-status 2>/dev/null)" && [ -n "$BATT" ]; then
    API_OK=1
    PCT="$(printf '%s' "$BATT" | sed -n 's/.*"percentage"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p')"
    PLUG="$(printf '%s' "$BATT" | sed -n 's/.*"plugged"[[:space:]]*:[[:space:]]*"\([A-Z_]*\)".*/\1/p')"
    ok "Termux:API responding — battery ${PCT:-?}%, plugged=${PLUG:-UNKNOWN}"
  else
    warn "termux-battery-status is installed but did not answer."
    warn "Install the Termux:API *APK* from F-Droid (same signature as Termux itself),"
    warn "then grant it battery + notification permissions. Without it the power governor"
    warn "in osiris_mobile.power fails open and heavy runs will NOT be throttled."
  fi
else
  warn "termux-battery-status not on PATH — power-aware routing disabled"
fi

# ── 4. Python virtualenv ──────────────────────────────────────────────────────
step "4/10  Python virtualenv"

have python || die "python not found after the pkg stage"
PYVER="$(python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "python        : $PYVER ($(command -v python))"
python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
  || die "OSIRIS targets Python 3.9+; found $PYVER"

# --system-site-packages is deliberate: it is how the venv sees the pkg-installed
# numpy/scipy instead of trying to compile them.
if [ -x "$VENV/bin/python" ]; then
  ok "venv exists: $VENV"
else
  python -m venv --system-site-packages "$VENV" || die "venv creation failed"
  ok "venv created: $VENV"
fi

PY="$VENV/bin/python"
"$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PY" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || warn "pip self-upgrade failed; continuing"
ok "pip $("$PY" -m pip --version | awk '{print $2}')"

if "$PY" -c 'import numpy' 2>/dev/null; then
  ok "numpy $("$PY" -c 'import numpy; print(numpy.__version__)') visible in venv"
else
  warn "numpy not visible; falling back to a pip build (slow)"
  "$PY" -m pip install "numpy>=1.24" || die "numpy install failed — OSIRIS cannot run without it"
fi

# ── 5. Pure-Python dependencies ───────────────────────────────────────────────
step "5/10  Python dependencies"

PIP_ARGS="--prefer-binary --no-cache-dir"
# shellcheck disable=SC2086
"$PY" -m pip install $PIP_ARGS "requests>=2.31" "jsonschema>=4.0" "pytest>=7.0" \
  || die "core pip dependencies failed"
ok "requests, jsonschema, pytest"

if [ "$TIER" != "lite" ]; then
  # shellcheck disable=SC2086
  "$PY" -m pip install $PIP_ARGS "PyYAML>=6.0" "rich>=13.0" || warn "PyYAML/rich install failed"
  if "$PY" -c 'import scipy' 2>/dev/null; then
    ok "scipy $("$PY" -c 'import scipy; print(scipy.__version__)') visible"
  else
    warn "scipy unavailable. The unified 'osiris' package declares it; modules that import"
    warn "it at module scope will fail. organism_sim and dnalang do not need it."
  fi
fi

if [ "$TIER" = "quantum" ]; then
  log "building qiskit from source — this is the long pole"
  export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"   # 8 parallel rustc jobs will OOM-kill
  # shellcheck disable=SC2086
  "$PY" -m pip install $PIP_ARGS "qiskit>=1.3" \
    && ok "qiskit $("$PY" -c 'import qiskit; print(qiskit.__version__)')" \
    || warn "qiskit build failed. Everything except dnalang's aer/ibm backends still works."
  # shellcheck disable=SC2086
  "$PY" -m pip install $PIP_ARGS "qiskit-aer>=0.15" \
    && ok "qiskit-aer" || warn "qiskit-aer build failed (expected on many Android NDK setups)"
fi

# ── 6. Source repositories ────────────────────────────────────────────────────
step "6/10  Source repositories"

fetch_repo() {   # fetch_repo <name>
  local name="$1" dest="$OSIRIS_SRC/$1"
  if [ -n "$LOCAL_SRC" ] && [ -d "$LOCAL_SRC/$name" ]; then
    if [ -e "$dest" ]; then
      log "using existing $dest"
    else
      cp -a "$LOCAL_SRC/$name" "$dest" && ok "copied $name from $LOCAL_SRC"
    fi
  elif [ -d "$dest/.git" ]; then
    ok "$name present ($(git -C "$dest" rev-parse --short HEAD 2>/dev/null || echo 'no HEAD')) — not pulled"
  elif [ -d "$dest" ]; then
    warn "$dest exists but is not a git checkout; leaving it alone"
  else
    git clone --depth 1 "$GH_ORG/$name.git" "$dest" >/dev/null 2>&1 \
      && ok "cloned $name" \
      || { warn "clone failed: $GH_ORG/$name.git"; return 1; }
  fi
}

# --no-deps everywhere: the dependency solve is done above, on purpose. dnalang declares
# qiskit>=1.3 but only imports it lazily inside Circuit.to_qiskit (dnalang/qc_ir.py:63),
# so the lite tier installs it without qiskit and the parser/sema/lower/rules path is
# fully functional. Resolving deps normally would drag in a 45-min Rust build for nothing.
install_repo() {  # install_repo <dir-name>
  local name="$1" dest="$OSIRIS_SRC/$1"
  [ -d "$dest" ] || { warn "skipping install of $name (not present)"; return 1; }
  "$PY" -m pip install --no-deps --no-build-isolation -e "$dest" >/dev/null 2>&1 \
    && ok "installed (editable, --no-deps): $name" \
    || { warn "editable install failed for $name"; return 1; }
}

for r in "${REPOS_LITE[@]}"; do fetch_repo "$r" && install_repo "$r" || true; done
if [ "$TIER" != "lite" ]; then
  for r in "${REPOS_FULL[@]}"; do fetch_repo "$r" && install_repo "$r" || true; done
fi

# This repo itself, if bootstrap was run from a checkout of it.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SELF_DIR/pyproject.toml" ]; then
  "$PY" -m pip install --no-deps --no-build-isolation -e "$SELF_DIR" >/dev/null 2>&1 \
    && ok "installed (editable): osiris-mobile-termux" \
    || warn "editable install of osiris-mobile-termux failed"
fi

# ── 7. llama.cpp (local inference backend) ────────────────────────────────────
step "7/10  llama.cpp inference backend"

if [ "$SKIP_LLAMA" -eq 1 ]; then
  log "skipped (--skip-llama)"
elif [ -x "$OSIRIS_HOME/bin/llama-server" ]; then
  ok "llama-server already built: $OSIRIS_HOME/bin/llama-server"
else
  LLAMA_DIR="$OSIRIS_SRC/llama.cpp"
  if [ ! -d "$LLAMA_DIR/.git" ]; then
    git clone --depth 1 "$LLAMA_REPO" "$LLAMA_DIR" >/dev/null 2>&1 \
      && ok "cloned llama.cpp" || warn "llama.cpp clone failed"
  else
    ok "llama.cpp checkout present"
  fi

  if [ -d "$LLAMA_DIR" ]; then
    # LLAMA_CURL=OFF drops the libcurl dependency; GGML_NATIVE=ON lets ggml pick up the
    # Tensor cores' dotprod/i8mm extensions, which is most of the CPU throughput.
    JOBS="$(nproc 2>/dev/null || echo 4)"
    [ "$JOBS" -gt 4 ] && JOBS=4          # more than 4 clang jobs OOM-kills on 8 GB phones
    log "configuring (jobs=$JOBS) — first build takes 10-20 min"
    if cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" \
         -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_NATIVE=ON \
         -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON \
         >"$OSIRIS_HOME/logs/llama_cmake.log" 2>&1
    then
      if cmake --build "$LLAMA_DIR/build" -j"$JOBS" --target llama-server llama-cli \
           >>"$OSIRIS_HOME/logs/llama_build.log" 2>&1
      then
        for b in llama-server llama-cli; do
          BIN="$(find "$LLAMA_DIR/build" -name "$b" -type f -perm -u+x 2>/dev/null | head -1)"
          [ -n "$BIN" ] && ln -sf "$BIN" "$OSIRIS_HOME/bin/$b" && ok "linked $b"
        done
      else
        warn "llama.cpp build failed — see $OSIRIS_HOME/logs/llama_build.log"
      fi
    else
      warn "llama.cpp cmake configure failed — see $OSIRIS_HOME/logs/llama_cmake.log"
    fi
  fi
fi

# ── 8. GGUF model ─────────────────────────────────────────────────────────────
step "8/10  Local model weights"

case "$MODEL_SIZE" in
  1.5b) MODEL_FILE="qwen2.5-1.5b-instruct-q4_k_m.gguf"
        MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/$MODEL_FILE"
        MODEL_MB=1100 ;;
  3b)   MODEL_FILE="qwen2.5-3b-instruct-q4_k_m.gguf"
        MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/$MODEL_FILE"
        MODEL_MB=2000 ;;
  none) MODEL_FILE=""; MODEL_URL=""; MODEL_MB=0 ;;
esac

if [ -z "$MODEL_FILE" ]; then
  log "skipped (--model-size none)"
elif [ -s "$OSIRIS_HOME/models/$MODEL_FILE" ]; then
  ok "model present: $MODEL_FILE ($(du -m "$OSIRIS_HOME/models/$MODEL_FILE" | cut -f1) MB)"
else
  log "downloading $MODEL_FILE (~${MODEL_MB} MB) — resumable"
  if have curl && curl -fL -C - --retry 3 --retry-delay 5 \
        -o "$OSIRIS_HOME/models/$MODEL_FILE.part" "$MODEL_URL"
  then
    mv "$OSIRIS_HOME/models/$MODEL_FILE.part" "$OSIRIS_HOME/models/$MODEL_FILE"
    ok "downloaded $MODEL_FILE"
  else
    warn "model download failed. Fetch it manually to $OSIRIS_HOME/models/ :"
    warn "  $MODEL_URL"
  fi
fi

# Deliberate default: 1.5B-Q4, not the desktop's qwen2.5:7b. A 7B Q4 is ~4.7 GB resident
# and Android's lowmemorykiller reaps it during any foreground app switch.

# ── 9. Environment file ───────────────────────────────────────────────────────
step "9/10  Environment file"

cat > "$OSIRIS_HOME/env.sh" <<ENVEOF
# Generated by bootstrap_termux.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ') — tier=$TIER
# Source this, or let ~/.bashrc do it.
export OSIRIS_HOME="$OSIRIS_HOME"
export OSIRIS_SRC="$OSIRIS_SRC"
export OSIRIS_VENV="$VENV"
export OSIRIS_TIER="$TIER"

# Inference backend. osiris_mobile.backends.ollama_shim translates Ollama's /api/chat
# onto llama-server's OpenAI-compatible /v1/chat/completions, so osiris_brain.py's
# OSIRIS_OLLAMA contract is preserved unchanged.
export OSIRIS_LLAMA_BIN="$OSIRIS_HOME/bin/llama-server"
export OSIRIS_MODEL_PATH="$OSIRIS_HOME/models/${MODEL_FILE:-}"
export OSIRIS_MODEL="${MODEL_FILE%.gguf}"
export OSIRIS_OLLAMA="http://127.0.0.1:11434"
export OSIRIS_LLAMA_PORT="8080"

# Mobile survival envelope (read by osiris_mobile.power and .store).
export OSIRIS_BATTERY_FLOOR="20"        # percent; below this, heavy workers pause
export OSIRIS_BATTERY_RESUME="35"       # percent; hysteresis so we do not flap
export OSIRIS_THERMAL_CEILING="45"      # degrees C
export OSIRIS_AUDIT_WINDOW="512"        # bounded AuditChain ring — OOM-killer defence
export OSIRIS_CHECKPOINT_EVERY="1"      # seeds between checkpoint flushes
export OSIRIS_RESULTS="$OSIRIS_HOME/results"
export OSIRIS_CHECKPOINTS="$OSIRIS_HOME/checkpoints"
export OSIRIS_TELEMETRY="$OSIRIS_HOME/telemetry"

export PATH="$OSIRIS_HOME/bin:\$PATH"

osiris-activate() { . "$VENV/bin/activate"; }
ENVEOF
ok "wrote $OSIRIS_HOME/env.sh"

BASHRC="$HOME/.bashrc"
MARKER="# >>> osiris-mobile >>>"
if ! grep -qF "$MARKER" "$BASHRC" 2>/dev/null; then
  {
    echo ""
    echo "$MARKER"
    echo "[ -f \"$OSIRIS_HOME/env.sh\" ] && . \"$OSIRIS_HOME/env.sh\""
    echo "# <<< osiris-mobile <<<"
  } >> "$BASHRC"
  ok "hooked $BASHRC"
else
  log "$BASHRC already hooked"
fi

# ── 10. Doctor ────────────────────────────────────────────────────────────────
step "10/10  Doctor"

FAILED=0
check() {  # check <label> <python-expr>
  if "$PY" -c "$2" >/dev/null 2>&1; then
    ok "$1"
  else
    printf '    %s[fail]%s %s\n' "$C_E" "$C_R" "$1"
    FAILED=$((FAILED + 1))
  fi
}
soft_check() {
  if "$PY" -c "$2" >/dev/null 2>&1; then ok "$1"; else warn "$1 — unavailable"; fi
}

check "numpy"                    "import numpy"
check "dnalang (front end)"      "import dnalang; dnalang.parse; dnalang.check"
check "dnalang.action_dsl"       "from dnalang.action_dsl import parse_sexpr"
check "dnalang.regulation"       "from dnalang.regulation import Trigger"
check "organism_sim.lcs"         "from organism_sim.lcs import PARAMS16, RuleEngine"
check "organism_sim.agent"       "from organism_sim.agent import LCSAgent"
check "organism_sim.grn"         "import organism_sim.grn"
check "organism_sim.telemetry"   "from organism_sim.telemetry import capture_frame"
check "organism_sim.chat_bridge" "import organism_sim.chat_bridge"
check "6-mux benchmark"          "from organism_sim.benchmarks.mux import run_single, run_split"

if [ "$TIER" != "lite" ]; then
  soft_check "scipy"          "import scipy"
  soft_check "osiris package" "import osiris; osiris.LAMBDA_PHI"
  soft_check "LivLM"          "import osiris_livlm"
  soft_check "qbyte_system"   "from qbyte_system.qbyte import Qbyte"
fi
if [ "$TIER" = "quantum" ]; then
  soft_check "qiskit"     "import qiskit"
  soft_check "qiskit-aer" "import qiskit_aer"
fi

[ -x "$OSIRIS_HOME/bin/llama-server" ] && ok "llama-server binary" || warn "llama-server not built"
[ -n "$MODEL_FILE" ] && [ -s "$OSIRIS_HOME/models/$MODEL_FILE" ] && ok "model weights" || warn "no model weights"
[ "$API_OK" -eq 1 ] && ok "Termux:API" || warn "Termux:API not responding (install the F-Droid APK)"

printf '\n%s────────────────────────────────────────────────%s\n' "$C_B" "$C_R"
if [ "$FAILED" -eq 0 ]; then
  printf '%s OSIRIS mobile lab ready (tier: %s)%s\n' "$C_G$C_B" "$TIER" "$C_R"
else
  printf '%s %d core check(s) failed (tier: %s)%s\n' "$C_E$C_B" "$FAILED" "$TIER" "$C_R"
fi
cat <<NEXTEOF

  Next:
    exec bash -l                     # pick up ~/.osiris/env.sh
    ./launch_fold.sh                 # fold-aware tmux lab (REPL | telemetry)
    termux-wake-lock                 # before any long run, or Doze will suspend it

  Long runs must use setsid, not plain nohup — plain nohup dies with the Termux session:
    setsid nohup \$OSIRIS_VENV/bin/python experiments/<rung>.py 5 \\
      > \$OSIRIS_RESULTS/<rung>_stdout.log 2>&1 < /dev/null &

NEXTEOF
printf '%s────────────────────────────────────────────────%s\n' "$C_B" "$C_R"

exit "$([ "$FAILED" -eq 0 ] && echo 0 || echo 1)"
