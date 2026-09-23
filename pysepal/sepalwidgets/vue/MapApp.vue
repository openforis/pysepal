<template>
  <v-app
    :class="{ 'narrow-mode': isNarrow, 'narrow-bottom-panel': narrowBottom }"
    :style="{
      '--drawer-width': sidebarOffset,
      '--right-panel-width': rightPanelOffset,
      '--right-panel-open': rightPanelOpen ? '1' : '0',
      '--narrow-panel-height': NARROW_PANEL_HEIGHT,
      '--bottom-panel-height': narrowBottom ? NARROW_PANEL_HEIGHT : '0px',
    }"
  >
    <div
      v-if="main_map && main_map.length > 0"
      id="map-container"
      class="map-background"
      @click="handleMapClick"
    >
      <jupyter-widget :widget="main_map[0]"></jupyter-widget>
    </div>

    <div
      v-if="activeStep && activeStep.display === 'step'"
      class="step-content-container"
      :class="{ 'right-panel-open': rightPanelOpen }"
    >
      <jupyter-widget
        v-for="(widget, i) in activeStep.content"
        :key="`step-content-${i}`"
        :widget="widget"
      ></jupyter-widget>
    </div>

    <v-navigation-drawer
      v-model="drawer"
      :mini-variant="mini"
      :mini-variant-width="collapsedWidth"
      :width="expandedWidth"
      :class="['left-drawer', { 'drawer-disabled': drawerDisabled }]"
      app
      permanent
      stateless
    >
      <div style="display: flex; flex-direction: column; height: 100%">
        <div class="drawer-header">
          <div class="app-title">
            <v-icon class="mr-2">{{
              app_icon ? app_icon : "mdi-earth"
            }}</v-icon>
            <span class="title font-weight-medium">{{ app_title }}</span>
          </div>

          <v-spacer></v-spacer>
          <v-btn
            v-if="!mini"
            icon
            @click="togglePin"
            class="pin-btn"
            :title="is_pinned ? 'Unpin sidebar' : 'Pin sidebar'"
          >
            <v-icon small>{{
              is_pinned ? "mdi-pin" : "mdi-pin-outline"
            }}</v-icon>
          </v-btn>
        </div>

        <v-divider class="ma-0 pa-0"></v-divider>

        <div
          class="drawer-top"
          style="flex: 1; overflow-y: auto; overflow-x: hidden"
        >
          <!-- steps -->
          <v-list dense class="pa-0 ma-0">
            <v-tooltip
              right
              :disabled="!mini"
              v-if="main_map && main_map.length > 0"
            >
              <template v-slot:activator="{ on, attrs }">
                <v-list-item
                  @click="showMainMap"
                  :class="{ 'active-step': !activeStepId }"
                  v-bind="attrs"
                  v-on="on"
                >
                  <v-list-item-icon>
                    <v-icon class="mb-1">mdi-map</v-icon>
                  </v-list-item-icon>
                  <v-list-item-content v-if="!mini">
                    <v-list-item-title class="font-weight-medium"
                      >Map</v-list-item-title
                    >
                  </v-list-item-content>
                </v-list-item>
              </template>
              <span>Map</span>
            </v-tooltip>

            <v-tooltip
              right
              :disabled="!mini"
              v-for="(step, i) in steps"
              :key="`step-${i}`"
            >
              <template v-slot:activator="{ on, attrs }">
                <v-list-item
                  @click="activateStep(step)"
                  :class="{
                    'active-step':
                      activeStepId === step.id &&
                      step.content_enabled !== false,
                  }"
                  :data-step-id="step.id"
                  v-bind="attrs"
                  v-on="on"
                >
                  <v-list-item-icon>
                    <v-icon class="mb-1">{{
                      step.icon || "mdi-checkbox-blank-circle-outline"
                    }}</v-icon>
                  </v-list-item-icon>
                  <v-list-item-content v-if="!mini">
                    <v-list-item-title class="font-weight-medium">{{
                      step.name
                    }}</v-list-item-title>
                  </v-list-item-content>
                </v-list-item>
              </template>
              <span>{{ step.name }}</span>
            </v-tooltip>
          </v-list>
        </div>

        <div class="drawer-bottom" style="padding: 16px 0">
          <v-divider class="mb-4"></v-divider>
          <!-- helper steps -->
          <v-list class="pa-0 ma-0" dense>
            <v-tooltip
              right
              :disabled="!mini"
              v-for="(link, i) in externalLinks"
              :key="`external-${i}`"
            >
              <template v-slot:activator="{ on, attrs }">
                <v-list-item
                  :href="link.url"
                  target="_blank"
                  class="link-item"
                  link
                  v-bind="attrs"
                  v-on="on"
                >
                  <v-list-item-icon>
                    <v-icon class="mb-1">{{ link.icon }}</v-icon>
                  </v-list-item-icon>
                  <v-list-item-content v-if="!mini">
                    <v-list-item-title class="d-flex align-center">
                      {{ link.title }}
                      <v-spacer></v-spacer>
                      <v-icon small class="ml-1">mdi-open-in-new</v-icon>
                    </v-list-item-title>
                  </v-list-item-content>
                </v-list-item>
              </template>
              <span>{{ link.title }}</span>
            </v-tooltip>

            <v-divider class="mt-2 mb-4"></v-divider>

            <!-- configuration: theme + language -->
            <template v-if="!mini">
              <v-list-item>
                <v-list-item-content>
                  <v-list-item-title class="d-flex align-center justify-center">
                    <div>
                      <slot name="theme-toggle"></slot>
                      <jupyter-widget
                        :widget="theme_toggle[0]"
                      ></jupyter-widget>
                    </div>
                    <div>
                      <slot name="language-selector"></slot>
                      <jupyter-widget
                        :widget="language_selector[0]"
                      ></jupyter-widget>
                    </div>
                  </v-list-item-title>
                </v-list-item-content>
              </v-list-item>
            </template>
            <template v-else>
              <v-tooltip right>
                <template v-slot:activator="{ on, attrs }">
                  <v-list-item v-bind="attrs" v-on="on">
                    <v-list-item-icon class="config-icon-mini">
                      <slot name="theme-toggle"></slot>
                      <jupyter-widget
                        :widget="theme_toggle[0]"
                      ></jupyter-widget>
                    </v-list-item-icon>
                  </v-list-item>
                </template>
                <span>Toggle theme</span>
              </v-tooltip>
              <v-tooltip right>
                <template v-slot:activator="{ on, attrs }">
                  <v-list-item v-bind="attrs" v-on="on">
                    <v-list-item-icon class="config-icon-mini">
                      <slot name="language-selector"></slot>
                      <jupyter-widget
                        :widget="language_selector[0]"
                      ></jupyter-widget>
                    </v-list-item-icon>
                  </v-list-item>
                </template>
                <span>Change language</span>
              </v-tooltip>
            </template>
          </v-list>
        </div>
      </div>
    </v-navigation-drawer>

    <!-- Right Panel Component -->
    <jupyter-widget
      v-if="right_panel && right_panel.length > 0"
      :widget="right_panel[0]"
    ></jupyter-widget>

    <div class="sidebar-controls" :style="{ left: sidebarOffset }">
      <v-btn
        tile
        color="primary"
        @click="toggleDrawer"
        class="control-btn mb-2"
        :title="mini ? 'Expand sidebar' : 'Collapse sidebar'"
      >
        <v-icon>{{ mini ? "mdi-menu-right" : "mdi-menu-left" }}</v-icon>
      </v-btn>
    </div>

    <!-- main Area -->
    <v-main class="transparent-main" @click="handleMainClick"> </v-main>

    <!-- dialog for dialog-type steps -->
    <v-dialog
      v-model="open_dialog"
      :width="dialogWidthComputed"
      :height="dialogHeightComputed"
      :fullscreen="dialogFullscreen"
      :overlay="true"
      content-class="dialog-container"
      @click:outside="handleDialogOutsideClick"
    >
      <v-card class="dialog-card">
        <v-card-title class="headline d-flex justify-space-between">
          <span>{{ activeStep ? activeStep.name : "" }}</span>
          <v-btn icon @click="closeDialog">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="dialog-content pt-4">
          <template
            v-if="
              activeStep && activeStep.content && activeStep.content.length > 0
            "
          >
            <jupyter-widget
              v-for="(widget, i) in activeStep.content"
              :key="`dialog-content-${i}`"
              :widget="widget"
              class="jupyter-widget-container"
            ></jupyter-widget>
          </template>
        </v-card-text>

        <v-divider
          v-if="
            activeStep && activeStep.actions && activeStep.actions.length > 0
          "
        ></v-divider>

        <v-card-actions
          v-if="
            activeStep && activeStep.actions && activeStep.actions.length > 0
          "
        >
          <v-spacer></v-spacer>
          <v-btn
            v-for="(action, i) in activeStep.actions"
            :key="`action-${i}`"
            :text="action.cancel ? true : false"
            :outlined="action.cancel ? true : false"
            color="primary"
            small
            @click="handleActionClick(action)"
          >
            {{ action.label }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-app>
</template>

<script>
export default {
  name: "MapApp",

  props: {
    main_map: {
      type: Array,
      default: () => [],
    },
    steps_data: {
      type: Array,
      default: () => [],
    },
    right_panel_config: {
      type: Object,
      default: () => ({
        title: "Extra Content",
        icon: "mdi-widgets",
        width: 300,
        description: "",
        toggle_icon: "mdi-chevron-left",
      }),
    },
    right_panel_content: {
      type: Array,
      default: () => [],
    },
    right_panel: {
      type: Array,
      default: () => [],
    },
    right_panel_open: {
      type: Boolean,
      default: false,
    },
    right_panel_width: {
      type: Number,
      default: 300,
    },
    repo_url: {
      type: String,
      default: "https://github.com/sepal-contrib/",
    },
    docs_url: {
      type: String,
      default: "",
    },
    dialog_width: {
      type: [String, Number],
      default: 800,
    },
    dialog_fullscreen: {
      type: Boolean,
      default: false,
    },
    app_title: {
      type: String,
      default: "SEPAL Module",
    },
    app_icon: {
      type: String,
      default: "mdi-earth",
    },
    theme_toggle: {
      type: Array,
      default: () => [],
    },
    language_selector: {
      type: Array,
      default: () => [],
    },
    initial_step: {
      type: Number,
      default: null,
    },
    current_step: {
      type: Number,
      default: null,
    },
    step_open: {
      type: Boolean,
      default: false,
    },
    is_pinned: {
      type: Boolean,
      default: true,
    },
    drawer_width: {
      type: Number,
      default: 320,
    },
  },

  data: () => ({
    drawer: true,
    mini: false,
    collapsedWidth: 60,
    expandedWidth: 320,
    activeStepId: null,
    open_dialog: false,
    windowWidth: window.innerWidth,
    windowHeight: window.innerHeight,
    narrowBreakpoint: 960,
    // Single source of truth for the narrow-mode bottom-panel height,
    // shared between inline style bindings and the global layout vars
    // synced to the document root. The CSS rule that sizes the panel
    // reads this via `var(--narrow-panel-height)` so they can't drift.
    NARROW_PANEL_HEIGHT: "45vh",
  }),

  computed: {
    steps() {
      return this.steps_data;
    },

    activeStep() {
      if (!this.activeStepId) return null;
      return this.steps.find((step) => step.id === this.activeStepId);
    },

    sidebarOffset() {
      return this.mini ? this.collapsedWidth + "px" : this.expandedWidth + "px";
    },

    actualRightOffset() {
      // Use Vuetify's application service as the source of truth for the
      // right-side drawer offset.  This tracks the REAL drawer state
      // (open/closed) regardless of what Solara reconc does to the
      // right_panel_open traitlet.
      return this.$vuetify?.application?.right || 0;
    },

    rightPanelOffset() {
      return this.actualRightOffset + "px";
    },

    rightPanelOpen() {
      return this.actualRightOffset > 0;
    },

    externalLinks() {
      return [
        {
          title: "Source Code",
          icon: "mdi-code-braces",
          url: this.repo_url,
        },
        {
          title: "Documentation",
          icon: "mdi-book-open-page-variant",
          url: this.docs_url || `${this.repo_url}/blob/main/doc/en.rst`,
        },
        {
          title: "Report Bug",
          icon: "mdi-bug",
          url: `${this.repo_url}/issues/new`,
        },
      ];
    },

    dialogWidthComputed() {
      // Use reactive windowWidth instead of directly accessing window.innerWidth
      const viewportWidth = this.windowWidth;
      const sidebarWidth = this.mini ? this.collapsedWidth : this.expandedWidth;
      const maxDialogWidth = viewportWidth - sidebarWidth - 40;

      // Check if active step has a specific width
      let targetWidth = this.dialog_width;
      if (this.activeStep && this.activeStep.width) {
        targetWidth = this.activeStep.width;
      }

      if (typeof targetWidth === "string" && targetWidth.includes("%")) {
        const percentage = parseInt(targetWidth, 10) / 100;
        return Math.min(maxDialogWidth, viewportWidth * percentage);
      }

      return Math.min(maxDialogWidth, targetWidth || 800);
    },

    dialogHeightComputed() {
      // Check if active step has a specific height
      if (this.activeStep && this.activeStep.height) {
        // Use reactive windowHeight instead of directly accessing window.innerHeight
        const viewportHeight = this.windowHeight;
        const maxDialogHeight = viewportHeight - 80; // Leave some margin

        if (
          typeof this.activeStep.height === "string" &&
          this.activeStep.height.includes("%")
        ) {
          const percentage = parseInt(this.activeStep.height, 10) / 100;
          return Math.min(maxDialogHeight, viewportHeight * percentage);
        }

        return Math.min(maxDialogHeight, this.activeStep.height);
      }

      // Return null if no height is specified (let dialog auto-size)
      return null;
    },

    dialogFullscreen() {
      return this.dialog_fullscreen;
    },

    drawerDisabled() {
      return this.open_dialog;
    },

    isNarrow() {
      return this.windowWidth < this.narrowBreakpoint;
    },

    narrowBottom() {
      return this.isNarrow && this.rightPanelOpen;
    },
  },

  watch: {
    // Watch for current_step changes from Python
    current_step(newValue) {
      if (newValue !== null && newValue !== this.activeStepId) {
        const step = this.steps.find((s) => s.id === newValue);
        if (step) {
          this.activeStepId = newValue;
          if (step.display === "dialog") {
            this.open_dialog = true;
          }
        }
      } else if (newValue === null && this.activeStepId !== null) {
        this.activeStepId = null;
        this.open_dialog = false;
      }
    },

    // Watch for step_open changes from Python
    step_open(newValue) {
      if (!newValue && this.open_dialog) {
        this.open_dialog = false;
      } else if (
        newValue &&
        this.activeStep &&
        this.activeStep.display === "dialog"
      ) {
        this.open_dialog = true;
      }
    },

    // Sync layout variables to document root for sibling widgets (notifications).
    // Watches the actual Vuetify application offset (driven by the real
    // v-navigation-drawer state) instead of the right_panel_open prop, which
    // can be stale after a Solara reconc.  No debounce — the pill must move
    // in lockstep with the drawer's 0.3s animation.
    actualRightOffset() {
      this._syncGlobalLayoutVars();
    },
    sidebarOffset() {
      this._syncGlobalLayoutVars();
      this._pushDrawerWidth();
    },
    mini() {
      this._pushDrawerWidth();
    },

    // Toggle a body-level class while a step dialog is open so siblings
    // mounted outside the v-app stacking context (e.g. Legend, mounted via
    // its own jupyter-widget) can hide themselves cleanly.
    open_dialog: {
      immediate: true,
      handler(open) {
        document.body.classList.toggle("sepal-modal-open", !!open);
      },
    },

    // Nudge leaflet to recompute its canvas when the bottom-panel layout
    // toggles — the map-container's height changes via CSS, but leaflet
    // only listens to window resize. Also re-sync global layout vars so
    // Legend / NotificationUI stop tracking a right edge that no longer
    // exists in narrow-bottom mode.
    narrowBottom() {
      this._syncGlobalLayoutVars();
      this.$nextTick(() => {
        window.dispatchEvent(new Event("resize"));
      });
    },

    // Auto-collapse the drawer on narrow viewports regardless of pin state,
    // and restore the pinned-open state when the viewport grows back.
    isNarrow: {
      immediate: true,
      handler(narrow) {
        if (narrow) {
          if (!this.mini) this.mini = true;
        } else if (this.is_pinned && this.mini) {
          this.mini = false;
        }
        this._syncGlobalLayoutVars();
      },
    },
  },

  mounted() {
    window.addEventListener("resize", this.handleResize);
    // Once, at mount: rerunning it when steps_data changes (a language switch
    // renames the steps) would reopen a step the user has closed.
    this.autoActivateFirstStepIfNeeded();
    if (!this.is_pinned) {
      this.mini = true;
    }
    this._syncGlobalLayoutVars();
    this._pushDrawerWidth();
    this._pushWindowSize();
  },

  beforeDestroy() {
    window.removeEventListener("resize", this.handleResize);
    this._clearGlobalLayoutVars();
    document.body.classList.remove("sepal-modal-open");
  },

  methods: {
    _pushDrawerWidth() {
      // Report the real pixel width of the nav drawer to Python so the
      // embedded map can fit bounds against the visible region.
      const px = this.mini ? this.collapsedWidth : this.expandedWidth;
      if (px !== this.drawer_width) {
        this.set_drawer_width(px);
      }
    },
    _syncGlobalLayoutVars() {
      const root = document.documentElement;
      const offset = this.actualRightOffset;
      // In narrow-bottom mode the right panel is docked at the bottom, so
      // downstream consumers (Legend, notifications) should treat the right
      // edge as flush and instead leave room at the bottom.
      const rightOffset = this.narrowBottom ? 0 : offset;
      const isOpen = this.narrowBottom ? false : offset > 0;
      root.style.setProperty("--sepal-right-panel-width", rightOffset + "px");
      root.style.setProperty("--sepal-right-panel-open", isOpen ? "1" : "0");
      root.style.setProperty(
        "--sepal-notification-right-offset",
        rightOffset + "px"
      );
      root.style.setProperty("--sepal-drawer-width", this.sidebarOffset);
      // Reserved space at the bottom edge for floating components (Legend,
      // toasts) — equals the panel height when open, the toggle-tab height
      // when narrow + closed, else 0.
      const hasRightPanel = this.right_panel && this.right_panel.length > 0;
      let bottomReserved = "0px";
      if (this.narrowBottom) bottomReserved = this.NARROW_PANEL_HEIGHT;
      else if (this.isNarrow && hasRightPanel) bottomReserved = "48px";
      root.style.setProperty("--sepal-bottom-reserved", bottomReserved);
    },
    _clearGlobalLayoutVars() {
      const root = document.documentElement;
      root.style.removeProperty("--sepal-right-panel-width");
      root.style.removeProperty("--sepal-right-panel-open");
      root.style.removeProperty("--sepal-notification-right-offset");
      root.style.removeProperty("--sepal-drawer-width");
      root.style.removeProperty("--sepal-bottom-reserved");
    },
    handleResize() {
      // Update reactive window dimensions
      this.windowWidth = window.innerWidth;
      this.windowHeight = window.innerHeight;
      this._pushWindowSize();
      this.$forceUpdate();
    },

    _pushWindowSize() {
      // Report real browser size to Python so the embedded map has a
      // correct canvas size from render 0 (fixes first-fit zoom bug).
      this.set_window_size({ w: window.innerWidth, h: window.innerHeight });
    },

    toggleDrawer() {
      this.mini = !this.mini;
    },

    togglePin() {
      this.is_pinned = !this.is_pinned;
    },

    handleMapClick() {
      this.collapseIfNotPinned();
    },

    handleMainClick() {
      this.collapseIfNotPinned();
    },

    collapseIfNotPinned() {
      if (!this.is_pinned && !this.mini) {
        this.mini = true;
      }
    },

    handleRightPanelAction(action) {
      // Call Python method to handle right panel state
      // Note: Python method is vue_handle_right_panel_action, called without 'vue_' prefix
      this.handle_right_panel_action(action);
    },

    activateStep(step) {
      // Don't allow step activation if drawer is disabled (dialog is open)
      if (this.drawerDisabled) {
        return;
      }

      // Handle right panel actions first
      if (step.right_panel_action) {
        this.handleRightPanelAction(step.right_panel_action);
      }

      // Only change step content if step has content
      if (step.content && step.content.length > 0) {
        this.activeStepId = step.id;

        // For dialog display type, open the dialog
        if (step.display === "dialog") {
          this.open_dialog = true;
        } else {
          // Close dialog when activating non-dialog step
          this.open_dialog = false;
        }

        // Call Python method to sync step state
        this.handle_step_activation(step.id);

        this.$emit("step-activated", step);
      } else {
        // For action-only steps, provide visual feedback
        this.provideStepFeedback(step);
        this.$emit("step-action", step);
      }
    },

    closeDialog() {
      this.open_dialog = false;
      this.activeStepId = null;

      // Call Python method to sync step deactivation
      this.handle_step_deactivation();
    },

    handleDialogOutsideClick() {
      if (this.activeStep && this.activeStep.display === "dialog") {
        this.closeDialog();
      }
    },

    handleActionClick(action) {
      this.$emit("step-action", {
        step: this.activeStep,
        action: action,
      });

      if (action.close) {
        this.closeDialog();
      }

      if (action.next) {
        this.activeStepId = action.next;
        // Call Python method to sync step activation
        this.handle_step_activation(action.next);
      }
    },

    showMainMap() {
      // Don't allow if drawer is disabled (dialog is open)
      if (this.drawerDisabled) {
        return;
      }

      this.activeStepId = null;
      this.open_dialog = false;

      // Call Python method to sync step deactivation
      this.handle_step_deactivation();

      this.$emit("show-main-map");
    },

    provideStepFeedback(step) {
      // Add a temporary visual feedback for action-only steps
      // This could be enhanced with animations or other visual cues
      const stepElement = document.querySelector(`[data-step-id="${step.id}"]`);
      if (stepElement) {
        stepElement.style.transition = "background-color 0.2s ease";
        stepElement.style.backgroundColor =
          "var(--v-primary-lighten4, rgba(0, 0, 0, 0.1))";
        setTimeout(() => {
          stepElement.style.backgroundColor = "";
        }, 200);
      }
    },

    autoActivateFirstStepIfNeeded() {
      // Check if initial_step is specified
      if (this.initial_step !== null && !this.activeStepId) {
        const initialStep = this.steps.find(
          (step) => step.id === this.initial_step
        );
        if (
          initialStep &&
          initialStep.content &&
          initialStep.content.length > 0 &&
          initialStep.content_enabled !== false &&
          (initialStep.display === "step" || initialStep.display === "dialog")
        ) {
          this.$nextTick(() => {
            this.activeStepId = initialStep.id;

            // If it's a dialog step, open the dialog
            if (initialStep.display === "dialog") {
              this.open_dialog = true;
            }

            this.$emit("step-auto-activated", initialStep);
          });
          return;
        }
      }

      // Only auto-activate if:
      // 1. No main map is available
      // 2. No step is currently active
      // 3. There are steps available
      // 4. No initial_step was specified or it wasn't found
      const hasMainMap = this.main_map && this.main_map.length > 0;
      const hasSteps = this.steps && this.steps.length > 0;

      if (!hasMainMap && !this.activeStepId && hasSteps) {
        // Find the first step with content that can be displayed
        const firstStepWithContent = this.steps.find(
          (step) =>
            step.content &&
            step.content.length > 0 &&
            step.content_enabled !== false &&
            (step.display === "step" || step.display === "dialog")
        );

        if (firstStepWithContent) {
          // Use a small delay to ensure the component is fully mounted
          this.$nextTick(() => {
            this.activeStepId = firstStepWithContent.id;

            // If it's a dialog step, open the dialog
            if (firstStepWithContent.display === "dialog") {
              this.open_dialog = true;
            }

            this.$emit("step-auto-activated", firstStepWithContent);
          });
        }
      }
    },
  },
};
</script>

<style scoped>
.map-background {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 0;
}

/* Step content container */
.step-content-container {
  position: fixed;
  top: 0;
  left: var(--drawer-width);
  right: 0;
  bottom: 0;
  z-index: 0;
  background-color: var(--v-background-base, #f5f5f5);
  padding: 16px;
  transition: left 0.3s ease, right 0.3s ease;
}

/* When right panel is open, adjust step content */
.step-content-container.right-panel-open {
  right: var(--right-panel-width);
}

.transparent-main {
  background-color: transparent !important;
  z-index: 1;
  pointer-events: none; /* Allow clicking through to the map */
}

.drawer-header {
  display: flex;
  align-items: center;
  padding: 16px;
  height: 64px;
}

.app-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
}

/* New sidebar controls styling */
.sidebar-controls {
  position: fixed;
  z-index: 5 !important;
  top: 50%;
  transform: translateY(-50%);
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: left 0.3s ease;
  margin-left: -5px;
}

.control-btn {
  min-width: 25px !important;
  padding: 0px !important;
  margin-bottom: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  border-radius: 3px !important;
}

/* Mini-sidebar theme/language controls: center the embedded jupyter-widget
   inside the v-list-item-icon slot so the button aligns with the other
   icon rows (map/steps/links) instead of being clipped or left-aligned. */
.v-list-item .v-list-item__icon.config-icon-mini {
  margin: 0 !important;
  min-width: 0 !important;
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

/* The LocaleSelect renders as <v-menu><v-btn/></v-menu>; the menu wrapper
   (and any ipyvuetify wrapper div) can default to block-level width and
   push the btn to the left edge. Force every intermediate wrapper to flex
   so the btn itself gets centered, matching the ThemeToggle's <v-btn icon>
   which is already a square flex item. */
.config-icon-mini > *,
.config-icon-mini .v-menu,
.config-icon-mini .v-menu__activator {
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  width: 100%;
}

/* Collapse the LocaleSelect button to a circular icon button in mini mode,
   matching the ThemeToggle shape. Hide the language code text, drop the
   95px min-width, and kill the icon's right margin so it centers. */
.config-icon-mini .v-btn {
  min-width: 36px !important;
  width: 36px !important;
  height: 36px !important;
  padding: 0 !important;
  border-radius: 50% !important;
}
.config-icon-mini .v-btn .v-btn__content {
  font-size: 0 !important;
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  gap: 0 !important;
  width: 100%;
}
/* Target the locale icon specifically: kill its mr-2 margin and center
   the glyph absolutely inside the button so the trailing text node
   (rendered at font-size: 0) can't pull it left. */
.config-icon-mini .v-btn .v-btn__content .v-icon {
  font-size: 20px !important;
  margin: 0 !important;
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
}

.dialog-card {
  max-width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  margin: 0 auto !important;
}

.dialog-content {
  min-height: 200px;
  max-height: 70vh;
  overflow-y: auto;
  flex: 1;
}

.jupyter-widget-container {
  width: 100%;
  height: 100%;
}

/* Ensure interactive elements in the drawer can be clicked.

   The :not() guards are load-bearing, not tidiness. Vuetify disables a
   control with `.v-btn--disabled { pointer-events: none }` at specificity
   0,1,0; the selectors below are 0,2,0 and so used to win, handing every
   DISABLED button, list item and select in a drawer its pointer events back.
   The control stayed unclickable (the `disabled` attribute still applies),
   but it lit up on hover like a live one -- reported against the right
   panel's footer bar, and true of the navigation drawer just as much. */
.v-navigation-drawer .v-list-item:not(.v-list-item--disabled),
.v-navigation-drawer .v-btn:not(.v-btn--disabled),
.v-navigation-drawer .v-select:not(.v-input--is-disabled) {
  pointer-events: auto;
  transition: transform 0.3s ease;
}

/* Style active step */
.active-step {
  background-color: var(--v-primary-lighten4, rgba(0, 0, 0, 0.1));
}

/* override sepal-ui default css */
.full-screen-map > .leaflet-container {
  position: fixed !important;
  width: 100vw !important;
  height: 100vh !important;
  z-index: 100;
  bottom: 0;
  left: 0;
}

/* The scrim is deliberately NOT overridden. It used to be forced to
   `position: fixed` at `100vw/100vh` to cover a map that outranked it, but the
   app's layers now sit below vuetify's baseline so the default
   (`absolute`, inset 0 inside a fixed `.v-overlay`) already covers the
   viewport. Pinning explicit viewport units also made resizing visibly lag:
   vuetify declares `transition: .3s` with no property, i.e. `all`, so an
   explicit width/height ANIMATES to its new size on every resize (measured at
   ~296ms) while inset-based sizing settles in ~2ms. */

/* Ensure right panel is below dialog overlay */
.v-application .jupyter-widget {
  position: relative;
  z-index: 160 !important;
}

#map-container .leaflet-left {
  transition: left 0.3s ease;
  left: var(--drawer-width) !important;
}

#map-container .leaflet-right {
  transition: right 0.3s ease;
  right: calc(var(--right-panel-width) * var(--right-panel-open)) !important;
}

.v-application a {
  color: inherit;
  text-decoration: underline;
}

.link-item {
  color: inherit;
  text-decoration: none !important;
}

/* Disabled drawer when dialog is open */
.drawer-disabled {
  pointer-events: none !important;
  /* opacity: 0.6 !important; */
}

.drawer-disabled .v-list-item {
  pointer-events: none !important;
}

/* Narrow viewports: dock the right panel to the bottom and shrink the map
   above it. Despite the right-panel widget being mounted via a separate
   jupyter-widget, these scoped rules still apply in the ipyvue runtime —
   moving them to a non-scoped block was tried and broke the layout, so
   they stay here. The panel height is read from --narrow-panel-height so
   it cannot drift from the JS value used elsewhere for layout offsets.

   `narrow-mode` (always when narrow) reshapes the right-panel into a bottom
   sheet so its open/close transition slides vertically instead of from the
   right edge. `narrow-bottom-panel` (narrow + open) drives the layout shift
   for siblings: map shrinks upward, left drawer height shrinks, etc. */
.narrow-mode .right-panel.v-navigation-drawer {
  top: auto !important;
  left: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  width: 100vw !important;
  max-width: 100vw !important;
  height: var(--narrow-panel-height, 45vh) !important;
  box-shadow: 0 -2px 18px rgba(0, 0, 0, 0.12) !important;
  transition: transform 0.3s ease !important;
}
.narrow-mode .right-panel.v-navigation-drawer--close,
.narrow-mode .right-panel.v-navigation-drawer:not(.v-navigation-drawer--open) {
  transform: translateY(100%) !important;
}
.narrow-mode .right-panel.v-navigation-drawer--open {
  transform: translateY(0) !important;
}

/* In narrow mode the map ALWAYS reserves the bottom-panel height, even
   when the panel is closed. This keeps the visible map area stable so
   downstream calculations (e.g. image centering against the map size)
   don't shift every time the panel toggles. The closed-panel state shows
   an empty band below the map where the panel tab sits; the open panel
   slides in on top of that band. */
.narrow-mode #map-container.map-background {
  bottom: var(--narrow-panel-height, 45vh) !important;
}

.narrow-mode #map-container .leaflet-right {
  right: 0 !important;
  transition: none !important;
}
.narrow-mode #map-container .leaflet-left {
  transition: none !important;
}

/* Left drawer should only span the visible map area, not run behind the
   bottom panel. Vuetify positions the drawer with top:0 + height:100%; we
   shrink height (and pin bottom) so it stops at the panel's top edge. */
.narrow-mode .left-drawer.v-navigation-drawer {
  transition: height 0.3s ease, bottom 0.3s ease,
    transform 0.2s cubic-bezier(0.25, 0.8, 0.5, 1) !important;
}
.narrow-bottom-panel .left-drawer.v-navigation-drawer {
  height: calc(100vh - var(--bottom-panel-height)) !important;
  bottom: var(--bottom-panel-height) !important;
}

/* Step-type content (when used instead of the map) must also leave room
   for the bottom panel. */
.narrow-bottom-panel .step-content-container {
  bottom: var(--bottom-panel-height);
}

/* Re-center the sidebar collapse/expand arrow on the visible map area. */
.narrow-bottom-panel .sidebar-controls {
  top: calc((100vh - var(--bottom-panel-height)) / 2);
}

/* Right-panel toggle tab: when narrow, dock it flush to the bottom-center
   so the panel slides up from below it. The button flips orientation —
   on the right edge it is a vertical tab (25px short axis = width); at
   the bottom it becomes a horizontal tab (25px short axis = height) so
   the visible "thickness" matches in both layouts. */
.narrow-mode .right-panel-tab {
  top: auto !important;
  right: auto !important;
  bottom: 0 !important;
  left: 50% !important;
  transform: translateX(-50%) !important;
}
.narrow-mode .right-panel-tab .control-btn {
  min-width: 64px !important;
  height: 25px !important;
  padding: 0 !important;
  margin-bottom: 0 !important;
  border-radius: 3px 3px 0 0 !important;
  box-shadow: 0 -2px 6px rgba(0, 0, 0, 0.12) !important;
}
.narrow-mode .right-panel-tab .v-icon {
  transform: rotate(90deg);
}
</style>
