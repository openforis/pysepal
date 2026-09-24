<template>
  <div :class="{ 'right-panel-active': internalOpen }">
    <!-- Right side panel for extra content -->
    <v-navigation-drawer
      v-if="isExtraContentAvailable"
      v-model="internalOpen"
      :width="config.width || 300"
      app
      right
      stateless
      class="right-panel"
      hide-overlay
    >
      <div style="display: flex; flex-direction: column; height: 100%">
        <div class="drawer-header">
          <div class="app-title">
            <v-icon class="mr-2">{{ config.icon || "mdi-widgets" }}</v-icon>
            <span class="title font-weight-medium">{{
              config.title || "Extra Content"
            }}</span>
          </div>
          <v-spacer></v-spacer>
          <v-btn icon @click="close" class="pin-btn" title="Close panel">
            <v-icon small>mdi-close</v-icon>
          </v-btn>
        </div>

        <!-- Main panel description -->
        <div v-if="config.description" class="panel-description pa-3">
          <p class="body-2 ma-0 text--secondary">
            {{ config.description }}
          </p>
        </div>

        <v-divider class="ma-0 pa-0"></v-divider>

        <div
          class="drawer-top"
          style="flex: 1; overflow-y: auto; overflow-x: hidden"
        >
          <div class="pa-4">
            <div
              v-for="(section, sectionIndex) in content_data"
              :key="`section-${sectionIndex}`"
              class="mb-4"
            >
              <!-- Section header if title/icon provided -->
              <div
                v-if="section.title || section.icon"
                class="section-header mb-3"
              >
                <div class="d-flex align-center">
                  <v-icon v-if="section.icon" small class="mr-2">{{
                    section.icon
                  }}</v-icon>
                  <span
                    v-if="section.title"
                    class="subtitle-2 font-weight-medium"
                    >{{ section.title }}</span
                  >
                </div>
              </div>

              <!-- Section description -->
              <div v-if="section.description" class="section-description mb-3">
                <p class="body-2 ma-0 text--secondary">
                  {{ section.description }}
                </p>
              </div>

              <!-- Section content widgets -->
              <div
                v-for="(widget, widgetIndex) in section.content"
                :key="`section-${sectionIndex}-widget-${widgetIndex}`"
                class="mb-3"
              >
                <jupyter-widget :widget="widget"></jupyter-widget>
              </div>

              <!-- Optional divider -->
              <v-divider
                v-if="section.divider && sectionIndex < content_data.length - 1"
                class="mt-4"
              ></v-divider>
            </div>
          </div>
        </div>

        <!-- Footer: outside .drawer-top so it stays put while the sections
             scroll. No padding: a full-bleed bar could not remove it. -->
        <div v-if="hasFooter" class="drawer-footer">
          <v-divider class="ma-0 pa-0"></v-divider>
          <jupyter-widget
            v-for="(widget, footerIndex) in footer_content"
            :key="`footer-${footerIndex}`"
            :widget="widget"
          ></jupyter-widget>
        </div>
      </div>
    </v-navigation-drawer>

    <!-- Right panel toggle tab -->
    <div
      v-if="isExtraContentAvailable && !internalOpen && !disabled"
      class="right-panel-tab"
    >
      <v-btn
        tile
        color="secondary"
        @click="toggle"
        class="control-btn"
        title="Show extra content"
      >
        <v-icon>{{ config.toggle_icon || "mdi-menu-left" }}</v-icon>
      </v-btn>
    </div>
  </div>
</template>

<script>
export default {
  name: "RightPanel",

  props: {
    is_open: {
      type: Boolean,
      default: false,
    },
    config: {
      type: Object,
      default: () => ({
        title: "Extra Content",
        icon: "mdi-widgets",
        width: 300,
        description: "",
        toggle_icon: "mdi-menu-left",
      }),
    },
    content_data: {
      type: Array,
      default: () => [],
    },
    footer_content: {
      type: Array,
      default: () => [],
    },
    disabled: {
      type: Boolean,
      default: false,
    },
  },

  data() {
    return {
      internalOpen: false, // Initialize as false, will be set by watcher
    };
  },

  computed: {
    isExtraContentAvailable() {
      return this.content_data && this.content_data.length > 0;
    },
    hasFooter() {
      return this.footer_content && this.footer_content.length > 0;
    },
  },

  watch: {
    is_open(newValue) {
      this.internalOpen = newValue;
    },
    internalOpen(newValue) {
      if (newValue !== this.is_open) {
        // Emit the change to the parent component
        this.$emit("input", newValue);
        // Also emit a specific event for state changes - call Python method directly
        this.panel_state_changed(newValue);
      }
    },
  },

  mounted() {
    // Initialize internal state from prop after component is mounted
    this.internalOpen = this.is_open;
  },

  methods: {
    toggle() {
      this.internalOpen = !this.internalOpen;
      // Call Python method directly with boolean value
      this.panel_state_changed(this.internalOpen);
    },

    close() {
      this.internalOpen = false;
      // Call Python method directly with boolean value
      this.panel_state_changed(false);
    },
  },
};
</script>

<style scoped>
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

/* Right panel styles */

.right-panel.v-navigation-drawer {
  box-shadow: -2px 0 18px rgba(0, 0, 0, 0.08) !important;
}

.right-panel .section-header {
  padding: 8px 0;
  border-bottom: 1px solid var(--v-divider-base, rgba(0, 0, 0, 0.12));
  margin-bottom: 12px;
}

/* Description styling for both main panel and sections */
.panel-description {
  background-color: var(--v-background-lighten1, rgba(0, 0, 0, 0.05));
  border-radius: 4px;
}

.section-description {
  padding-left: 16px;
  margin-top: 8px;
}

/* Footer: never shrinks, so the sections scroll instead */
.drawer-footer {
  flex: 0 0 auto;
}

/* Right panel toggle tab */
.right-panel-tab {
  position: fixed;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
  z-index: 6 !important;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.right-panel-tab .control-btn {
  min-width: 25px !important;
  padding: 0px !important;
  margin-bottom: 8px;
  box-shadow: -2px 0 6px rgba(0, 0, 0, 0.12) !important;
  border-radius: 3px 0 0 3px !important;
}
</style>
