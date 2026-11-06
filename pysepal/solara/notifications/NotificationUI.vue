<template>
  <div :class="{ 'theme-dark': is_dark, 'theme-light': !is_dark }">
    <!-- Toast Stack: fixed top-right -->
    <div class="toast-stack">
      <v-alert
        v-for="toast in visibleToasts"
        :key="toast.id"
        :type="toast.kind !== 'cancel' ? toast.color : undefined"
        :value="true"
        dense
        dark
        elevation="4"
        class="toast-alert"
        :class="'toast-' + toast.kind"
        @click.native="_dismissToast(toast.id)"
      >
        <span class="toast-message">{{ toast.message }}</span>
        <span v-if="toast.count > 1" class="toast-count"
          >(x{{ toast.count }})</span
        >
        <div
          v-if="toast.timeout"
          class="toast-progress"
          :style="{ animationDuration: toast.timeout + 's' }"
        ></div>
      </v-alert>
    </div>

    <!-- Task Progress Pill / Logger -->
    <div
      class="pill-wrapper"
      :class="{ 'transitions-enabled': transitionsEnabled }"
    >
      <!-- Open: show only the log panel (with its own close button) -->
      <div v-if="logOpen" class="pill-log">
        <div class="pill-log-header">
          <span>
            <v-icon small class="mr-2">mdi-history</v-icon>
            Logger
          </span>
          <v-btn icon x-small @click="logOpen = false">
            <v-icon small>mdi-close</v-icon>
          </v-btn>
        </div>
        <div ref="logBody" class="pill-log-body" @scroll="_onLogScroll">
          <div v-if="logEntries.length === 0" class="pill-log-empty">
            No activity yet.
          </div>
          <div
            v-for="entry in logEntries"
            :key="entry.key"
            class="pill-log-line"
            :class="'log-' + entry.level"
          >
            <span class="pill-log-time">{{ entry.time }}</span>
            <span class="pill-log-level">{{ entry.levelLabel }}</span>
            <span class="pill-log-msg">{{ entry.message }}</span>
          </div>
        </div>
      </div>

      <!-- Closed: show pill (running task) + log button -->
      <div v-else class="pill-row">
        <div v-if="displayTask" class="pill-container">
          <v-progress-circular
            :indeterminate="pillProgress == null"
            :value="pillProgress == null ? 0 : pillProgress * 100"
            :size="14"
            :width="2"
            class="mr-2 pill-ring"
          />
          <span v-if="pillPct" class="pill-pct">{{ pillPct }}</span>
          <span :key="pillFrameB" class="pill-text pill-swap">{{
            pillText
          }}</span>
        </div>

        <v-btn
          icon
          class="pill-log-btn"
          title="Show log"
          @click="logOpen = true"
        >
          <v-icon>mdi-history</v-icon>
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "NotificationUI",
  props: {
    toasts: { type: Array, default: () => [] },
    tasks: { type: Array, default: () => [] },
    is_dark: { type: Boolean, default: false },
  },
  data() {
    return {
      dismissTimers: {},
      dismissedIdsList: [],
      logOpen: false,
      logFollowing: true, // Auto-scroll to bottom when new entries arrive
      transitionsEnabled: false, // Gated so the pill doesn't slide in on mount
      pillFrameB: false, // Alternation frame: false = title, true = progress detail
    };
  },
  computed: {
    visibleToasts() {
      const dismissed = new Set(this.dismissedIdsList);
      const active = this.toasts.filter((t) => !dismissed.has(t.id));
      active.sort((a, b) => b.created_at - a.created_at);
      return active.slice(0, 5);
    },
    runningTask() {
      const running = this.tasks.filter((t) => t.status === "running");
      return running.length > 0 ? running[running.length - 1] : null;
    },
    displayTask() {
      // Only show the pill while a task is actively running.
      // Finished tasks disappear — the user can open the log for history.
      return this.runningTask;
    },
    pillProgress() {
      const t = this.displayTask;
      return t && t.progress != null ? t.progress : null;
    },
    pillHasDetail() {
      // A detail is shown whenever it is set, including on an
      // indeterminate task (no numeric progress yet — e.g. a wait reason).
      const t = this.displayTask;
      return !!(t && t.progressDetail);
    },
    pillPct() {
      // Leading percentage, shown only on the progress-detail frame, and
      // only once progress is known — an indeterminate task's detail
      // stands alone, with no bogus percentage in front of it.
      if (
        !this.pillFrameB ||
        !this.pillHasDetail ||
        this.pillProgress == null
      ) {
        return null;
      }
      return Math.round(this.pillProgress * 100) + "%";
    },
    pillText() {
      if (!this.displayTask) return "Task log";
      const t = this.displayTask;
      // Progress-publishing tasks alternate between the run position
      // (title) and the current item's own progress (progressDetail).
      if (this.pillHasDetail) {
        return this.pillFrameB ? t.progressDetail : t.title;
      }
      let label = t.title;
      if (t.lastStep) {
        label += " — " + t.lastStep;
      }
      return label;
    },
    logEntries() {
      // Build a chronological log: START / STEP / DONE / FAIL per task
      const entries = [];
      for (const task of this.tasks) {
        // START entry
        entries.push({
          key: task.id + "-start",
          timestamp: task.createdAt || 0,
          level: "start",
          levelLabel: "START",
          message: task.title,
        });
        // STEP entries (one per milestone)
        if (task.milestones) {
          for (let i = 0; i < task.milestones.length; i++) {
            const ms = task.milestones[i];
            entries.push({
              key: task.id + "-ms-" + i,
              timestamp: ms.timestamp || 0,
              level: "step",
              levelLabel: "STEP",
              message: ms.message,
            });
          }
        }
        // DONE / FAIL / CANCEL entry
        if (task.status === "completed") {
          entries.push({
            key: task.id + "-done",
            timestamp: task.completedAt || 0,
            level: "done",
            levelLabel: "DONE",
            message: task.title,
          });
        } else if (task.status === "failed") {
          entries.push({
            key: task.id + "-fail",
            timestamp: task.completedAt || 0,
            level: "fail",
            levelLabel: "FAIL",
            message: task.errorMessage || task.title,
          });
        } else if (task.status === "cancelled") {
          entries.push({
            key: task.id + "-cancel",
            timestamp: task.completedAt || 0,
            level: "cancel",
            levelLabel: "CNCL",
            message: task.title,
          });
        }
      }
      // Sort chronologically (oldest first, like a real log)
      entries.sort((a, b) => a.timestamp - b.timestamp);
      // Format timestamps as HH:MM:SS
      for (const e of entries) {
        if (e.timestamp) {
          const d = new Date(e.timestamp * 1000);
          const hh = String(d.getHours()).padStart(2, "0");
          const mm = String(d.getMinutes()).padStart(2, "0");
          const ss = String(d.getSeconds()).padStart(2, "0");
          e.time = `${hh}:${mm}:${ss}`;
        } else {
          e.time = "--:--:--";
        }
      }
      return entries;
    },
  },
  watch: {
    toasts(newToasts) {
      this._syncToastTimers(newToasts);
    },
    logEntries() {
      // When new log entries arrive, scroll to bottom (if user was following)
      if (this.logOpen && this.logFollowing) {
        this.$nextTick(() => this._scrollLogToBottom());
      }
    },
    logOpen(isOpen) {
      // When opening the log, jump to the bottom and re-enable following
      if (isOpen) {
        this.logFollowing = true;
        this.$nextTick(() => this._scrollLogToBottom());
      }
    },
  },
  mounted() {
    this._syncToastTimers(this.toasts);
    // Enable the right-edge transition only AFTER initial layout has
    // settled — the RightPanel v-navigation-drawer registers with
    // $vuetify.application a few ticks after MapApp mounts, which in turn
    // drives the --sepal-notification-right-offset CSS var.  Gating with a
    // short timeout lets that first position lock in instantly (no slide).
    setTimeout(() => {
      this.transitionsEnabled = true;
    }, 400);
    // Alternate the pill between its title and progress-detail frames.
    // The timer always ticks (cheap); the flag only flips while a task
    // actually carries a detail, so detail-less tasks never alternate.
    this._pillFrameTimer = setInterval(() => {
      this.pillFrameB = this.pillHasDetail ? !this.pillFrameB : false;
    }, 2500);
  },
  beforeDestroy() {
    for (const id of Object.keys(this.dismissTimers)) {
      clearTimeout(this.dismissTimers[id]);
    }
    clearInterval(this._pillFrameTimer);
  },
  methods: {
    _syncToastTimers(newToasts) {
      // Set up auto-dismiss timers for new toasts with timeouts
      for (const toast of newToasts) {
        if (toast.timeout && !this.dismissTimers[toast.id]) {
          const toastId = toast.id;
          this.dismissTimers[toastId] = setTimeout(() => {
            this._dismissToast(toastId);
          }, toast.timeout * 1000);
        }
      }
      // Clean up timers and dismissed IDs for removed toasts
      const currentIds = new Set(newToasts.map((t) => t.id));
      for (const id of Object.keys(this.dismissTimers)) {
        if (!currentIds.has(id)) {
          clearTimeout(this.dismissTimers[id]);
          delete this.dismissTimers[id];
        }
      }
      this.dismissedIdsList = this.dismissedIdsList.filter((id) =>
        currentIds.has(id)
      );
    },
    _dismissToast(id) {
      // Clear any pending timer for this toast
      if (this.dismissTimers[id]) {
        clearTimeout(this.dismissTimers[id]);
        delete this.dismissTimers[id];
      }
      // Instantly hide in Vue (array push is reactive in Vue 2)
      if (!this.dismissedIdsList.includes(id)) {
        this.dismissedIdsList.push(id);
      }
      // Notify Python to clean up bus state (async)
      this.dismiss_toast(id);
    },
    _scrollLogToBottom() {
      const el = this.$refs.logBody;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    },
    _onLogScroll() {
      const el = this.$refs.logBody;
      if (!el) return;
      // Detect if user is at (or near) the bottom — if so, keep following.
      const distanceFromBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight;
      this.logFollowing = distanceFromBottom < 20;
    },
    _iconForStatus(status) {
      switch (status) {
        case "running":
          return "mdi-progress-clock";
        case "completed":
          return "mdi-check-circle";
        case "failed":
          return "mdi-alert-circle";
        case "cancelled":
          return "mdi-cancel";
        default:
          return "mdi-circle-outline";
      }
    },
  },
};
</script>

<style scoped>
/* ─── Toast Stack ────────────────────────────────────────── */
.toast-stack {
  position: fixed;
  top: 4px;
  right: 4px;
  /* Stay above Vuetify dialogs and their overlays so toasts remain visible
   * even when a modal is open — notifications are often about the dialog
   * itself (errors, progress) and cannot be hidden beneath it. */
  z-index: 9999;
  width: 440px;
  max-width: calc(100vw - 8px);
  max-height: calc(100vh - 8px);
  pointer-events: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
}

.toast-alert {
  pointer-events: auto;
  cursor: pointer;
  margin-bottom: 0 !important;
  border-radius: 6px;
  color: #ffffff !important;
  position: relative;
  overflow: hidden;
  min-height: 72px !important;
  padding-top: 20px !important;
  padding-bottom: 20px !important;
}

/* v-alert paints a filled background on its inner .v-alert__wrapper — force
 * that wrapper transparent and set the color on .toast-alert itself.  Use
 * `background-color` (not the shorthand) to avoid clearing other background
 * properties Vuetify sets. */
.toast-alert >>> .v-alert__wrapper {
  background-color: transparent !important;
}

/* Translucent backgrounds tuned per theme.
 * Colors picked to mirror the Vuetify button palette:
 *  - success = theme success green
 *  - error   = theme error red (matches color="error" buttons like Cancel)
 *  - warning = theme warning orange
 *  - info    = theme info blue
 */

/* Dark theme (default — theme success #3f802a, theme error #a63228) */
.theme-dark > .toast-stack .toast-alert.toast-success {
  background-color: rgba(63, 128, 42, 0.9) !important;
}
.theme-dark > .toast-stack .toast-alert.toast-info {
  background-color: rgba(21, 101, 192, 0.9) !important;
}
.theme-dark > .toast-stack .toast-alert.toast-warning {
  background-color: rgba(230, 120, 0, 0.9) !important;
}
.theme-dark > .toast-stack .toast-alert.toast-error {
  background-color: rgba(166, 50, 40, 0.92) !important;
  border-left: 4px solid #ffcdd2 !important;
}
.theme-dark > .toast-stack .toast-alert.toast-cancel {
  background-color: rgba(120, 120, 120, 0.9) !important;
}

/* Light theme — success matches the primary button green #5BB624,
 * error matches Vuetify's default error #ff5252 (color="error" buttons). */
.theme-light > .toast-stack .toast-alert.toast-success {
  background-color: rgba(91, 182, 36, 0.9) !important;
}
.theme-light > .toast-stack .toast-alert.toast-info {
  background-color: rgba(33, 150, 243, 0.9) !important;
}
.theme-light > .toast-stack .toast-alert.toast-warning {
  background-color: rgba(251, 140, 0, 0.9) !important;
}
.theme-light > .toast-stack .toast-alert.toast-error {
  background-color: rgba(255, 82, 82, 0.92) !important;
  border-left: 4px solid #ffcdd2 !important;
}
.theme-light > .toast-stack .toast-alert.toast-cancel {
  background-color: rgba(150, 150, 150, 0.9) !important;
}

/* Align icon and content properly */
.toast-alert >>> .v-alert__wrapper {
  align-items: center;
}

.toast-alert >>> .v-alert__content {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  line-height: 1.45;
  max-height: 400px;
  overflow-y: auto;
  color: #ffffff;
}

.toast-alert >>> .v-icon {
  color: #ffffff !important;
}

.toast-message {
  font-size: 0.92em;
  font-weight: 400;
  word-wrap: break-word;
  word-break: break-word;
  white-space: pre-wrap;
  flex: 1;
  color: #ffffff;
}

.toast-count {
  margin-left: 6px;
  opacity: 0.85;
  font-size: 0.85em;
}

.toast-alert.toast-error >>> .v-alert__content {
  max-height: 500px;
}

/* Auto-dismiss progress bar (shrinks over toast.timeout seconds) */
.toast-progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  background-color: rgba(255, 255, 255, 0.85);
  transform-origin: left center;
  animation-name: toast-progress-shrink;
  animation-timing-function: linear;
  animation-fill-mode: forwards;
  animation-iteration-count: 1;
}

@keyframes toast-progress-shrink {
  from {
    transform: scaleX(1);
  }
  to {
    transform: scaleX(0);
  }
}

/* ─── Task Progress Pill ─────────────────────────────────── */
.pill-wrapper {
  position: fixed;
  bottom: 8px;
  right: calc(var(--sepal-notification-right-offset, 0px) + 8px);
  /* Below vuetify's modal baseline, unlike the toast stack: the scrim should
   * dim the pill and the logger rather than let them float over a dialog.
   * See the layering contract in frontend/css/base.css. */
  z-index: 170;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  max-width: 500px;

  /* Theme-aware CSS vars (defaults = dark theme) */
  --pill-bg: rgba(33, 33, 33, 0.88);
  --pill-bg-hover: rgba(60, 60, 60, 0.94);
  --pill-fg: #ffffff;
  --pill-border: rgba(255, 255, 255, 0.08);
  --log-bg: rgba(33, 33, 33, 0.9);
  --log-fg: #e0e0e0;
  --log-time: #9e9e9e;
  --log-muted: #bdbdbd;
  --log-start: #64b5f6;
  --log-done: #81c784;
  --log-fail: #e57373;
  --log-divider: rgba(255, 255, 255, 0.12);
}

.pill-wrapper.transitions-enabled {
  transition: right 0.3s ease;
}

.theme-light > .pill-wrapper {
  --pill-bg: rgba(250, 250, 250, 0.88);
  --pill-bg-hover: rgba(240, 240, 240, 0.94);
  --pill-fg: #212121;
  --pill-border: rgba(0, 0, 0, 0.08);
  --log-bg: rgba(252, 252, 252, 0.9);
  --log-fg: #212121;
  --log-time: #616161;
  --log-muted: #757575;
  --log-start: #1976d2;
  --log-done: #388e3c;
  --log-fail: #d32f2f;
  --log-divider: rgba(0, 0, 0, 0.08);
}

.pill-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pill-container {
  display: flex;
  align-items: center;
  padding: 6px 14px;
  background-color: var(--pill-bg) !important;
  color: var(--pill-fg);
  border-radius: 4px;
  font-size: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

/* Icons inside the pill use the foreground color */
.pill-container >>> .v-icon {
  color: var(--pill-fg) !important;
}

.pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 420px;
}

/* Progress ring inherits the pill foreground (was hardcoded white, which
 * disappeared on the light pill).  v-progress-circular strokes with
 * currentColor when no color prop is given. */
.pill-ring {
  color: var(--pill-fg);
}

/* Leading percentage on the progress-detail frame */
.pill-pct {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-right: 8px;
  flex-shrink: 0;
}

/* Quick fade when the pill alternates frames, so the swap reads as
 * intentional rather than flickering */
.pill-swap {
  animation: pill-frame-fade 0.35s ease;
}

@keyframes pill-frame-fade {
  from {
    opacity: 0.15;
  }
  to {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pill-swap {
    animation: none;
  }
}

/* Always-visible log button (v-btn icon, square override)
 * NOTE: Vuetify's v-btn paints its background through a ::before overlay,
 * so we must force that overlay to transparent and set the real
 * background-color on the button element itself.  `background-color` is
 * used explicitly (not the `background` shorthand) to avoid wiping the
 * other background-* properties Vuetify may set.
 */
.pill-log-btn.v-btn {
  flex-shrink: 0;
  background-color: var(--pill-bg) !important;
  border-radius: 4px !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
  width: 36px !important;
  height: 36px !important;
  min-width: 36px !important;
  min-height: 36px !important;
}

.pill-log-btn.v-btn::before {
  background-color: transparent !important;
}

.pill-log-btn.v-btn:hover {
  background-color: var(--pill-bg-hover) !important;
}

.pill-log-btn >>> .v-icon {
  color: var(--pill-fg) !important;
}

/* Expanded log panel */
.pill-log {
  background-color: var(--log-bg) !important;
  color: var(--log-fg);
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  width: 420px;
  max-width: 90vw;
}

.pill-log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 6px 4px 12px;
  font-size: 12px;
  font-weight: 500;
  border-bottom: 1px solid var(--log-divider);
}

.pill-log-header >>> .v-icon {
  color: var(--log-fg) !important;
}

.pill-log-body {
  padding: 6px 12px;
  max-height: 180px;
  overflow-y: auto;
  font-size: 11px;
  line-height: 1.5;
}

.pill-log-empty {
  text-align: center;
  opacity: 0.6;
  font-style: italic;
  padding: 8px 0;
}

.pill-log-line {
  display: flex;
  align-items: flex-start;
  padding: 1px 0;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.5;
}

.pill-log-time {
  color: var(--log-time);
  flex-shrink: 0;
  margin-right: 8px;
}

.pill-log-level {
  flex-shrink: 0;
  margin-right: 8px;
  font-weight: 600;
  width: 38px;
}

.pill-log-msg {
  flex: 1;
  word-break: break-word;
  white-space: pre-wrap;
}

.log-start .pill-log-level {
  color: var(--log-start);
}
.log-step .pill-log-level {
  color: var(--log-muted);
}
.log-step .pill-log-msg {
  opacity: 0.85;
}
.log-done .pill-log-level {
  color: var(--log-done);
}
.log-fail .pill-log-level,
.log-fail .pill-log-msg {
  color: var(--log-fail);
}
.log-cancel .pill-log-level,
.log-cancel .pill-log-msg {
  color: var(--log-muted);
}
</style>
