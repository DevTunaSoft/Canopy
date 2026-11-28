#!/usr/bin/env bash
# Native Plasma 6 / Canopy Classic 5-minute idle sampler (guest-side, read-only /proc).
# Piped to the guest: ssh ... canopy@127.0.0.1 'bash -s STOCK 300 5' < this-file
# Emits raw TSV on stdout; no guest files, packages, services or settings are changed.
set -u
LABEL="${1:-UNLABELLED}"
DURATION="${2:-300}"
INTERVAL="${3:-5}"
CLK=$(getconf CLK_TCK)
printf '# schema=native-idle-sample/1 label=%s duration=%s interval=%s clk_tck=%s\n' "$LABEL" "$DURATION" "$INTERVAL" "$CLK"
printf '# utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '# host=vm guest=%s kernel=%s\n' "$(hostname)" "$(uname -r)"
printf '# column_set: t_rel_s pid comm utime_ticks stime_ticks rss_kib pss_kib vol_ctx invol_ctx nr_wakeups sys_user_ticks sys_nice_ticks sys_system_ticks sys_idle_ticks sys_iowait_ticks\n'

# Exact process set for this run, chosen by role (never by substring guessing).
pids() {
  for pattern in '^/usr/bin/startplasma-x11$' '^/usr/bin/kwin_x11 ' '^/usr/bin/plasmashell ' '^/home/canopy/.local/bin/canopy-classic$' '^/home/canopy/.*canopy-classic' ; do
    for p in $(pgrep -f "$pattern" 2>/dev/null); do printf '%s\n' "$p"; done
  done | sort -un
}
PIDS=$(pids | tr '\n' ',')
printf '# pids=%s\n' "$PIDS"

sys_ticks() {
  awk '/^cpu /{printf "%s %s %s %s %s\n",$2,$3,$4,$5,$6}' /proc/stat
}

start=$(date +%s)
n=0
while :; do
  now=$(date +%s)
  t=$((now-start))
  st=$(sys_ticks)
  for pid in $(pids); do
    [ -r "/proc/$pid/stat" ] || continue
    # /proc/pid/stat comm may contain spaces/parentheses: split after final ')'.
    line=$(cat "/proc/$pid/stat" 2>/dev/null) || continue
    rest=${line##*) }
    arr=($rest)
    # arr[0] is original field 3: utime(14)->11, stime(15)->12, rss(24)->21.
    utime=${arr[11]}; stime=${arr[12]}
    comm=$(printf '%s' "$line" | sed 's/^.*(\(.*\)).*/\1/')
    rss_pages=${arr[21]}
    pss_kib=$(awk '/^Pss:/{print $2}' "/proc/$pid/smaps_rollup" 2>/dev/null)
    [ -n "$pss_kib" ] || pss_kib=NA
    vol=$(awk -F: '/^voluntary_ctxt_switches:/{gsub(/ /,"",$2);print $2}' "/proc/$pid/status" 2>/dev/null)
    invol=$(awk -F: '/^nonvoluntary_ctxt_switches:/{gsub(/ /,"",$2);print $2}' "/proc/$pid/status" 2>/dev/null)
    wake=$(awk -F: '/^se.nr_wakeups:/{gsub(/ /,"",$2);print $2}' "/proc/$pid/sched" 2>/dev/null)
    printf 'S %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s\n' "$t" "$pid" "$comm" "$utime" "$stime" "$((rss_pages*4))" "$pss_kib" "${vol:-NA}" "${invol:-NA}" "${wake:-NA}" $st
  done
  n=$((n+1))
  [ "$t" -ge "$DURATION" ] && break
  sleep "$INTERVAL"
done
printf '# samples=%s elapsed_s=%s\n' "$n" "$t"
printf '# end_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
