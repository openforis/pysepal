<template>
  <v-row class="d-flex align-center mx-2 pysepal-file-input-root">
    <v-menu
      v-model="showFileMenu"
      :min-width="500"
      :max-width="500"
      :close-on-content-click="false"
      offset-y
      bottom
      :nudge-bottom="10"
      eager
    >
      <template v-slot:activator="{ on }">
        <v-btn v-on="on" color="primary" class="mr-2 pysepal-file-input-btn">
          <v-icon left small>fa-solid fa-search</v-icon>
          <span class="pysepal-file-input-label">{{ label }}</span>
        </v-btn>
      </template>

      <v-card class="pt-2">
        <!-- Search field -->
        <v-text-field
          ref="searchField"
          v-model="searchQuery"
          label="Search files"
          prepend-inner-icon="fa-solid fa-filter"
          clearable
          @click:clear="searchQuery = ''"
          @keydown="handleKeydown"
          class="mx-4 mb-1"
        ></v-text-field>

        <!-- Breadcrumb navigation -->
        <div class="px-4 pb-2 pysepal-file-input-crumbs">
          <v-breadcrumbs
            :items="breadcrumbItems"
            class="pa-0 pysepal-file-input-crumbs-list"
          >
            <template v-slot:divider>
              <v-icon small>fa-solid fa-chevron-right</v-icon>
            </template>
            <template v-slot:item="{ item }">
              <v-breadcrumbs-item
                :disabled="item.disabled"
                @click="navigateToPath(item.path)"
                class="pysepal-file-input-crumb"
                :title="item.tooltip || item.text"
              >
                <v-icon v-if="item.isHome" small>fa-solid fa-home</v-icon>
                <span v-else>{{ item.text }}</span>
              </v-breadcrumbs-item>
            </template>
          </v-breadcrumbs>
        </div>

        <v-progress-linear
          v-if="loading"
          indeterminate
          background-color="menu"
        />

        <!-- File list -->
        <v-list
          ref="fileList"
          color="menu"
          flat
          dense
          :max-height="300"
          style="overflow: auto"
        >
          <div v-if="filteredItems.length">
            <v-list-item
              v-for="(item, index) in filteredItems"
              :key="item.path"
              @click="!isKeyboardNavigation && onFileSelect(item)"
              :class="{
                'pysepal-file-input-item--active': selectedIndex === index,
              }"
              :style="getItemStyle(index)"
            >
              <v-list-item-action>
                <v-icon :color="getIconColor(item)">
                  {{ getIconName(item) }}
                </v-icon>
              </v-list-item-action>
              <v-list-item-content>
                <v-list-item-title
                  :class="{
                    'pysepal-file-input-item__title--active':
                      selectedIndex === index,
                  }"
                  :style="getTitleStyle(index)"
                >
                  {{ item.name }}
                </v-list-item-title>
              </v-list-item-content>
              <v-list-item-action-text class="ml-1" v-if="item.type === 'file'">
                {{ formatFileSize(item.size) }}
              </v-list-item-action-text>
            </v-list-item>
          </div>

          <!-- No files message -->
          <v-list-item v-if="!filteredItems.length">
            <v-list-item-content class="text-center">
              <v-list-item-title class="font-italic text-grey">
                {{
                  searchQuery
                    ? 'No files matching "' + searchQuery + '"'
                    : getEmptyMsg()
                }}
              </v-list-item-title>
            </v-list-item-content>
          </v-list-item>
        </v-list>
      </v-card>
    </v-menu>

    <v-text-field
      v-model="value"
      readonly
      label="Selected file"
      class="ml-2 pysepal-file-input-field"
      :error-messages="getErrorMessages"
    >
      <template v-slot:append>
        <v-btn v-if="clearable" icon color="primary" @click.stop="reset">
          <v-icon>fa-solid fa-times</v-icon>
        </v-btn>
        <v-btn icon color="primary" @click.stop="reloadFiles">
          <v-icon>fa-solid fa-sync-alt</v-icon>
        </v-btn>
      </template>
    </v-text-field>
  </v-row>
</template>

<script>
export default {
  name: "FileInput",

  props: {
    file_list: {
      type: Array,
      default: () => [],
    },
    current_folder: {
      type: String,
      default: "/",
    },
    loading: {
      type: Boolean,
      default: false,
    },
    label: {
      type: String,
      default: "Select File",
    },
    value: {
      type: String,
      default: "",
    },
    clearable: {
      type: Boolean,
      default: false,
    },
    root: {
      type: String,
      default: "/",
    },
    reload_files: {
      type: Number,
      default: 0,
    },
    reset_prop: {
      type: Number,
      default: 0,
    },
    base_path: {
      type: String,
      default: "",
    },
    extensions: {
      type: Array,
      default: () => [],
    },
    error_messages: {
      type: Array,
      default: [],
    },
  },

  data() {
    return {
      showFileMenu: false,
      searchQuery: "",
      selectedIndex: null,
      isKeyboardNavigation: false,
    };
  },

  computed: {
    // Get items to display (exclude parent ".." item) and apply search filter
    filteredItems() {
      const items = this.file_list.filter((item) => item.name !== "..");

      if (!this.searchQuery) {
        return items;
      }

      return items.filter((item) =>
        item.name.toLowerCase().includes(this.searchQuery.toLowerCase())
      );
    },

    // Build breadcrumb items from current path
    breadcrumbItems() {
      const rootPath = this.normalizePath(this.root);
      const currentPath = this.normalizePath(this.current_folder);

      // For remote servers, root is empty string
      const isRemote = rootPath === "";

      const items = [
        {
          text: "Home",
          path: rootPath,
          disabled: currentPath === rootPath,
          isHome: true,
          tooltip: isRemote ? "/home/sepal-user/" : rootPath,
        },
      ];

      // Only add additional breadcrumbs if we're deeper than root
      if (currentPath !== rootPath) {
        // For remote: currentPath might be "folder1/folder2", root is ""
        // For local: currentPath might be "/home/user/folder1", root is "/home/user"
        let relativePath;

        if (isRemote) {
          // For remote, currentPath is already relative to root
          relativePath = currentPath;
        } else {
          // For local, check if current is within root
          if (currentPath.startsWith(rootPath)) {
            relativePath = currentPath.slice(rootPath.length);
            // Remove leading slash if present
            if (relativePath.startsWith("/")) {
              relativePath = relativePath.slice(1);
            }
          } else {
            // Not within root, just show home
            relativePath = "";
          }
        }

        // Split and build breadcrumb items
        if (relativePath) {
          const parts = relativePath.split("/").filter((p) => p);
          let buildPath = rootPath;

          parts.forEach((part, index) => {
            if (isRemote) {
              // For remote: build path without leading slash
              buildPath = buildPath === "" ? part : `${buildPath}/${part}`;
            } else {
              // For local: build path with proper slashes
              buildPath =
                buildPath === "/" ? `/${part}` : `${buildPath}/${part}`;
            }

            items.push({
              text: part,
              path: buildPath,
              disabled: index === parts.length - 1, // Current folder is disabled
              isHome: false,
            });
          });
        }
      }

      return items;
    },

    getErrorMessages() {
      return this.error_messages;
    },
  },

  watch: {
    searchQuery() {
      // Auto-select first item when searching
      if (this.searchQuery && this.filteredItems.length > 0) {
        this.selectedIndex = 0;
        this.scrollToSelected();
      } else {
        this.selectedIndex = null;
      }
    },

    filteredItems() {
      // Reset selection when the list changes (e.g., navigating to a new folder)
      // But keep selection if we're just filtering with search
      if (!this.searchQuery) {
        this.selectedIndex = null;
      }
    },

    showFileMenu(isOpen) {
      if (isOpen) {
        // Focus and select search field when menu opens
        this.focusSearchField();
      } else {
        // Clear search when menu closes
        this.searchQuery = "";
        this.selectedIndex = null;
      }
      this.isKeyboardNavigation = false;
    },
  },

  methods: {
    normalizePath(path) {
      // Handle empty string (remote root) and null/undefined
      if (path === null || path === undefined) {
        return "/";
      }
      // Empty string is valid for remote servers
      if (path === "") {
        return "";
      }
      // Remove trailing slash except for root "/"
      if (path !== "/" && path.endsWith("/")) {
        return path.slice(0, -1);
      }
      return path;
    },

    focusSearchField() {
      const attemptFocus = () => {
        const field = this.$refs.searchField;
        if (!field) {
          return false;
        }

        if (typeof field.focus === "function") {
          field.focus();
        }

        const input = field.$el?.querySelector("input");
        if (input) {
          input.focus();
          input.select();
          return true;
        }

        return false;
      };

      this.$nextTick(() => {
        let tries = 0;

        const schedule = () => {
          if (attemptFocus()) {
            return;
          }
          tries += 1;
          if (tries < 6) {
            setTimeout(schedule, 60);
          }
        };

        schedule();
      });
    },

    reloadFiles() {
      this.reload_files += 1;
    },

    getEmptyMsg() {
      return this.extensions.length
        ? `No files with extensions ${this.extensions.join(", ")}`
        : "No files available";
    },

    reset() {
      this.value = "";
      this.error_messages = [];
      this.reset_prop += 1;
    },

    navigateToPath(path) {
      const targetPath = this.normalizePath(path);
      const currentPath = this.normalizePath(this.current_folder);

      if (targetPath !== currentPath) {
        this.current_folder = targetPath;
        // Clear search and selection
        this.searchQuery = "";
        this.selectedIndex = null;
        // Refocus search field after navigation
        this.focusSearchField();
      } else if (this.current_folder !== targetPath) {
        this.current_folder = targetPath;
      }
    },

    navigateToParent() {
      const rootPath = this.normalizePath(this.root);
      const currentPath = this.normalizePath(this.current_folder);
      const isRemote = rootPath === "";

      if (currentPath === rootPath) {
        return;
      }

      const lastSlash = currentPath.lastIndexOf("/");
      let parentPath;

      if (isRemote) {
        // For remote: "" is root, "folder" goes to "", "folder/sub" goes to "folder"
        if (lastSlash === -1) {
          // No slash found, we're at a top-level folder, go to root
          parentPath = "";
        } else {
          // Go to parent folder
          parentPath = currentPath.slice(0, lastSlash);
        }
      } else {
        // For local: normal path handling
        parentPath = lastSlash > 0 ? currentPath.slice(0, lastSlash) : "/";

        // Ensure we don't go above root
        if (!parentPath.startsWith(rootPath)) {
          parentPath = rootPath;
        }
      }

      this.navigateToPath(parentPath);
    },

    onFileSelect(item) {
      if (item.type === "directory") {
        // Navigate to folder
        this.current_folder = item.path;
        // Clear search and selection, refocus
        this.searchQuery = "";
        this.selectedIndex = null;
        this.focusSearchField();
      } else {
        // File selected - set value and close menu
        this.value = this.base_path
          ? this.base_path + "/" + item.path
          : item.path;
        this.showFileMenu = false;
      }
    },

    getItemStyle(index) {
      if (this.selectedIndex === index) {
        return {
          backgroundColor: "rgba(25, 118, 210, 0.16)",
          borderLeft: "3px solid var(--v-primary-base, #1976d2)",
        };
      }
      return {};
    },

    getTitleStyle(index) {
      if (this.selectedIndex === index) {
        return {
          fontWeight: 600,
          color: "var(--v-primary-base, #1976d2)",
        };
      }
      return {};
    },

    handleKeydown(event) {
      const maxIndex = this.filteredItems.length - 1;

      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          if (this.selectedIndex === null) {
            this.selectedIndex = 0;
          } else if (this.selectedIndex < maxIndex) {
            this.selectedIndex++;
          }
          this.scrollToSelected();
          break;
        case "ArrowUp":
          event.preventDefault();
          if (this.selectedIndex === null) {
            this.selectedIndex = 0;
          } else if (this.selectedIndex > 0) {
            this.selectedIndex--;
          }
          this.scrollToSelected();
          break;
        case "ArrowLeft":
          event.preventDefault();
          this.navigateToParent();
          break;
        case "ArrowRight":
          event.preventDefault();
          if (!this.filteredItems.length) {
            break;
          }
          if (this.selectedIndex === null) {
            this.selectedIndex = 0;
            this.scrollToSelected();
            break;
          }
          const selectedItem = this.filteredItems[this.selectedIndex];
          if (selectedItem && selectedItem.type === "directory") {
            this.isKeyboardNavigation = true;
            this.onFileSelect(selectedItem);
            setTimeout(() => {
              this.isKeyboardNavigation = false;
            }, 100);
          }
          break;
        case "Enter":
          event.preventDefault();
          if (this.filteredItems.length > 0 && this.selectedIndex !== null) {
            this.isKeyboardNavigation = true;
            this.onFileSelect(this.filteredItems[this.selectedIndex]);
            setTimeout(() => {
              this.isKeyboardNavigation = false;
            }, 100);
          }
          break;
      }
    },

    scrollToSelected() {
      this.$nextTick(() => {
        const listEl = this.$refs.fileList?.$el;
        if (listEl) {
          const selectedItem = listEl.querySelector(
            ".pysepal-file-input-item--active"
          );
          if (selectedItem) {
            selectedItem.scrollIntoView({
              block: "nearest",
              behavior: "smooth",
            });
          }
        }
      });
    },

    getFileMetadata(item) {
      const fileMetadata = {
        "": { color: "primary_contrast", icon: "fa-regular fa-folder" },
        ".csv": { color: "secondary_contrast", icon: "fa-solid fa-table" },
        ".txt": { color: "secondary_contrast", icon: "fa-solid fa-table" },
        ".tif": { color: "secondary_contrast", icon: "fa-regular fa-image" },
        ".tiff": { color: "secondary_contrast", icon: "fa-regular fa-image" },
        ".png": { color: "secondary_contrast", icon: "fa-regular fa-image" },
        ".vrt": { color: "secondary_contrast", icon: "fa-regular fa-image" },
        ".shp": {
          color: "secondary_contrast",
          icon: "fa-solid fa-vector-square",
        },
        ".ipynb": { color: "green", icon: "fa-regular fa-file-code" },
        ".py": { color: "secondary_contrast", icon: "fa-regular fa-file-code" },
        ".json": {
          color: "secondary_contrast",
          icon: "fa-regular fa-file-code",
        },
        ".geojson": {
          color: "secondary_contrast",
          icon: "fa-solid fa-vector-square",
        },
        ".gpkg": {
          color: "secondary_contrast",
          icon: "fa-solid fa-vector-square",
        },
        ".pdf": { color: "secondary_contrast", icon: "fa-regular fa-file-pdf" },
        ".zip": {
          color: "secondary_contrast",
          icon: "fa-regular fa-file-archive",
        },
        ".log": { color: "secondary_contrast", icon: "fa-regular fa-file-alt" },
        DEFAULT: { color: "anchor", icon: "fa-regular fa-file" },
      };

      if (item.type === "directory") {
        return fileMetadata[""];
      }

      const ext = item.name.slice(item.name.lastIndexOf(".")).toLowerCase();
      return fileMetadata[ext] || fileMetadata["DEFAULT"];
    },

    getIconName(item) {
      return this.getFileMetadata(item).icon;
    },

    getIconColor(item) {
      return this.getFileMetadata(item).color;
    },

    formatFileSize(bytes) {
      if (!bytes) return "";
      const units = ["B", "KB", "MB", "GB"];
      let size = bytes;
      let unit = 0;
      while (size >= 1024 && unit < units.length - 1) {
        size /= 1024;
        unit++;
      }
      return Math.round(size * 100) / 100 + " " + units[unit];
    },
  },
};
</script>

<style>
/* Every rule lives here. ipyvuetify loads this file as a runtime template, not
   a compiled SFC, so a `<style scoped>` block is dropped outright -- one lived
   here for a while and none of its rules ever reached the page. Nothing scopes
   these either, hence the `pysepal-file-input-` prefix on every class. */
.pysepal-file-input-root {
  container-type: inline-size;
  container-name: pysepal-file-input;
  flex-wrap: nowrap;
}
@container pysepal-file-input (max-width: 450px) {
  .pysepal-file-input-label {
    display: none !important;
  }
  .pysepal-file-input-btn {
    min-width: 36px !important;
    padding: 0 8px !important;
  }
  .pysepal-file-input-btn .v-icon.v-icon--left {
    margin-right: 0 !important;
  }
}
@container pysepal-file-input (max-width: 300px) {
  .pysepal-file-input-field {
    display: none !important;
  }
}

/* Breadcrumbs: one line that scrolls sideways, each crumb ellipsised. */
.pysepal-file-input-crumbs {
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
}

.pysepal-file-input-crumbs::-webkit-scrollbar {
  height: 4px;
}

.pysepal-file-input-crumbs::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 2px;
}

.pysepal-file-input-crumbs-list {
  flex-wrap: nowrap !important;
  white-space: nowrap;
}

/* The class sits on the `v-breadcrumbs-item` itself, so it needs no descendant
   selector -- the old rule chained to `.v-breadcrumbs-item`, a class Vuetify
   does not emit (it is `.v-breadcrumbs__item`) on an element that was never a
   descendant. */
.pysepal-file-input-crumb {
  cursor: pointer;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.pysepal-file-input-crumb:hover:not([disabled]) {
  text-decoration: underline;
}

/* The highlight itself is inline style from getItemStyle/getTitleStyle; these
   only smooth the transition between rows. */
.pysepal-file-input-item--active {
  transition: background-color 120ms ease, border-left 120ms ease;
}

.pysepal-file-input-item__title--active {
  transition: color 120ms ease;
}
</style>
