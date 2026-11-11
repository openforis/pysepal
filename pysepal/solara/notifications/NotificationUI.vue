<template>
  <div :class="{ 'theme-dark': is_dark, 'theme-light': !is_dark }">
    <!-- Toast Stack: fixed top-right. The click is caught here because Vue 3
         has no `.native` and Vuetify 2's v-alert does not forward its clicks. -->
    <div class="toast-stack" @click="_onToastClick">
      <v-alert
        v-for="toast in visibleToasts"
        :key="toast.id"
        :type="toast.color"
        :icon="toast.kind === 'cancel' ? 'mdi-cancel' : undefined"
        v-bind="alertProps(toast)"
        elevation="4"
        class="toast-alert"
        :class="'toast-' + toast.kind"
        :data-toast-id="toast.id"
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
            <v-icon v-bind="iconSize('small')" class="mr-2">mdi-history</v-icon>
            Logger
          </span>
          <v-btn icon v-bind="logCloseBtnProps" @click="logOpen = false">
            <v-icon v-bind="iconSize('small')">mdi-close</v-icon>
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
            indeterminate
            :size="14"
            :width="2"
            class="mr-2"
            color="white"
          />
          <span class="pill-text">{{ pillText }}</span>
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
  // toasts, tasks and is_dark are traits: ipyvue adds them as data, and
  // declaring them as props too makes Vue 3 warn about the duplicate.
  data() {
    return {
      dismissTimers: {},
      dismissedIdsList: [],
      logOpen: false,
      logFollowing: true, // Auto-scroll to bottom when new entries arrive
      transitionsEnabled: false, // Gated so the pill doesn't slide in on mount
    };
  },
  computed: {
    v3() {
      return !!(
        this.$vuetify &&
        this.$vuetify.theme &&
        this.$vuetify.theme.global
      );
    },
    logCloseBtnProps() {
      // A Vuetify 3 icon button is elevated and 12px wider than its size; these
      // give back the flat 20px button of Vuetify 2.
      if (this.v3) {
        return { size: "x-small", density: "comfortable", variant: "text" };
      }
      return { "x-small": true };
    },
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
    pillText() {
      if (!this.displayTask) return "Task log";
      const t = this.displayTask;
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
  },
  // Vue 2 calls beforeDestroy, Vue 3 calls beforeUnmount.
  beforeDestroy() {
    this._clearDismissTimers();
  },
  beforeUnmount() {
    this._clearDismissTimers();
  },
  methods: {
    alertProps(toast) {
      const cancel = toast.kind === "cancel";
      const closable = !toast.timeout;
      if (this.v3) {
        return {
          variant: cancel ? "tonal" : "flat",
          closable,
          density: "compact",
        };
      }
      return {
        text: cancel,
        value: true,
        dismissible: closable,
        dense: true,
        dark: !cancel,
      };
    },
    iconSize(name) {
      // Vuetify 3's named icon sizes scale with the font; Vuetify 2's are
      // these pixels.
      return this.v3
        ? { size: { small: 16, "x-small": 12 }[name] }
        : { [name]: true };
    },
    _onToastClick(event) {
      const alert = event.target.closest("[data-toast-id]");
      if (alert) {
        this._dismissToast(alert.getAttribute("data-toast-id"));
      }
    },
    _clearDismissTimers() {
      for (const id of Object.keys(this.dismissTimers)) {
        clearTimeout(this.dismissTimers[id]);
      }
    },
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
  /* Stay above Vuetify dialogs and their overlays (~202 on Vuetify 2, 2000 on
   * Vuetify 3) so toasts remain visible even when a modal is open —
   * notifications are often about the dialog itself (errors, progress) and
   * cannot be hidden beneath it. */
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
  position: relative;
  overflow: hidden;
  min-height: 72px !important;
  padding-top: 20px !important;
  padding-bottom: 20px !important;
}

/* Filled toasts take the theme colours, as any filled alert does, so they match
 * the app's alerts and buttons in both themes. The opacity lets the map show
 * through a little, as the toasts always did. */
.toast-stack .toast-alert {
  opacity: 0.9;
}
.toast-stack .toast-alert.toast-error {
  border-left: 4px solid #ffcdd2 !important;
}

/* The tint is translucent, so the cancel toast sits on the card surface. */
.theme-dark > .toast-stack .toast-alert.toast-cancel {
  background-color: #1e1e1e !important;
}
.theme-light > .toast-stack .toast-alert.toast-cancel {
  background-color: #ffffff !important;
}
.toast-alert.toast-cancel .toast-progress {
  background-color: currentColor;
}

.toast-alert:not(.toast-cancel) {
  color: #ffffff !important;
}

/* `:deep()` reaches the elements Vuetify renders inside a component. Vuetify 3
 * honours it; ipyvue 1 injects this style uncompiled, so the browser drops these
 * rules on Vuetify 2, as it always dropped the deprecated combinator they
 * replace. */
.toast-alert :deep(.v-alert__content) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  line-height: 1.45;
  max-height: 400px;
  overflow-y: auto;
}

.toast-alert:not(.toast-cancel) :deep(.v-alert__content),
.toast-alert:not(.toast-cancel) :deep(.v-icon) {
  color: #ffffff !important;
}

.toast-message {
  font-size: 0.92em;
  font-weight: 400;
  word-wrap: break-word;
  word-break: break-word;
  white-space: pre-wrap;
  flex: 1;
}

.toast-count {
  margin-left: 6px;
  opacity: 0.85;
  font-size: 0.85em;
}

.toast-alert.toast-error :deep(.v-alert__content) {
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
.pill-container :deep(.v-icon) {
  color: var(--pill-fg) !important;
}

.pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 420px;
}

/* Always-visible log button (v-btn icon, square override)
 * NOTE: Vuetify's v-btn paints its hover background through an overlay
 * (::before on Vuetify 2, .v-btn__overlay on Vuetify 3), so we must force that
 * overlay to transparent and set the real background-color on the button
 * element itself.  `background-color` is used explicitly (not the `background`
 * shorthand) to avoid wiping the other background-* properties Vuetify may set.
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

/* A rule of its own: Vuetify 2 drops a rule whose selector list holds `:deep()`. */
.pill-log-btn.v-btn :deep(.v-btn__overlay) {
  background-color: transparent !important;
}

.pill-log-btn.v-btn:hover {
  background-color: var(--pill-bg-hover) !important;
}

.pill-log-btn :deep(.v-icon) {
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

.pill-log-header :deep(.v-icon) {
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
