<!-- Vuetify gives an unprefixed icon the mdi class and font; class: renders Font Awesome as is -->
<template>
  <v-row class="d-flex align-center mx-2 my-0 pysepal-file-input-root">
    <!-- width, not min-width: Vuetify caps a menu's min-width at its activator's width -->
    <v-menu
      v-model="showFileMenu"
      :width="500"
      :max-width="500"
      :close-on-content-click="false"
      location="bottom"
      :offset="10"
      eager
    >
      <template v-slot:activator="{ props }">
        <v-btn
          v-bind="props"
          color="primary"
          class="mr-2 pysepal-file-input-btn"
        >
          <v-icon start size="small">class:fa-solid fa-search</v-icon>
          <span class="pysepal-file-input-label">{{ label }}</span>
        </v-btn>
      </template>

      <v-card class="pt-2">
        <!-- Search field -->
        <v-text-field
          ref="searchField"
          v-model="searchQuery"
          label="Search files"
          prepend-inner-icon="class:fa-solid fa-filter"
          variant="underlined"
          color="primary"
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
              <v-icon size="small">class:fa-solid fa-chevron-right</v-icon>
            </template>
            <template v-slot:item="{ item }">
              <!-- title is a v-breadcrumbs-item prop (the label), so the tooltip goes on a span -->
              <v-breadcrumbs-item
                :disabled="item.disabled"
                @click="navigateToPath(item.path)"
                class="pysepal-file-input-crumb"
              >
                <span :title="item.tooltip || item.text">
                  <v-icon v-if="item.isHome" size="small"
                    >class:fa-solid fa-home</v-icon
                  >
                  <span v-else>{{ item.text }}</span>
                </span>
              </v-breadcrumbs-item>
            </template>
          </v-breadcrumbs>
        </div>

        <v-progress-linear
          v-if="loading"
          indeterminate
          color="primary"
          bg-color="menu"
        />

        <!-- File list -->
        <v-list
          ref="fileList"
          bg-color="menu"
          :max-height="300"
          class="pysepal-file-input-list"
          style="overflow: auto"
        >
          <div v-if="filteredItems.length">
            <v-list-item
              v-for="(item, index) in filteredItems"
              :key="item.path"
              :active="isSelected(item)"
              color="primary"
              @click="!isKeyboardNavigation && onFileSelect(item)"
              :class="{
                'pysepal-file-input-item--active': selectedIndex === index,
              }"
              :style="getItemStyle(index)"
            >
              <template v-slot:prepend>
                <v-icon
                  :icon="'class:' + getIconName(item)"
                  :color="getIconColor(item)"
                />
              </template>
              <v-list-item-title
                :class="{
                  'pysepal-file-input-item__title--active':
                    selectedIndex === index,
                }"
                :style="getTitleStyle(index)"
              >
                {{ item.name }}
              </v-list-item-title>
              <template v-slot:append>
                <span
                  v-if="item.type === 'file'"
                  class="ml-1 pysepal-file-input-size"
                >
                  {{ formatFileSize(item.size) }}
                </span>
                <!-- A folder row opens the folder, so a folder is selected with its check only -->
                <span
                  v-if="isCheckable(item)"
                  class="pysepal-file-input-check ml-2"
                  :class="{
                    'pysepal-file-input-check--on text-primary':
                      isSelected(item),
                  }"
                  :title="isSelected(item) ? 'Deselect' : 'Select'"
                  @click.stop="toggleFile(fullPath(item))"
                  @mousedown.stop
                >
                  <v-icon
                    size="small"
                    :color="isSelected(item) ? 'primary' : undefined"
                  >
                    class:fa-solid fa-check
                  </v-icon>
                </span>
              </template>
            </v-list-item>
          </div>

          <!-- No files message -->
          <v-list-item v-if="!filteredItems.length">
            <v-list-item-title class="font-italic text-grey text-center">
              {{
                searchQuery
                  ? 'No files matching "' + searchQuery + '"'
                  : getEmptyMsg()
              }}
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </v-card>
    </v-menu>

    <v-text-field
      v-if="!multiple"
      v-model="value"
      readonly
      label="Selected file"
      variant="underlined"
      color="primary"
      class="ml-2 pysepal-file-input-field"
      :error-messages="getErrorMessages"
    >
      <template v-slot:append-inner>
        <v-btn
          v-if="clearable"
          icon
          variant="text"
          density="comfortable"
          color="primary"
          @click.stop="reset"
        >
          <v-icon>class:fa-solid fa-times</v-icon>
        </v-btn>
        <v-btn
          icon
          variant="text"
          density="comfortable"
          color="primary"
          @click.stop="reloadFiles"
        >
          <v-icon>class:fa-solid fa-sync-alt</v-icon>
        </v-btn>
      </template>
    </v-text-field>

    <!-- One count chip; its menu lists the selected paths, a click removes one -->
    <v-select
      v-else
      :model-value="selectedPaths"
      :items="selectedPaths"
      multiple
      label="Selected files"
      no-data-text="No file selected"
      variant="underlined"
      color="primary"
      item-color="primary"
      menu-icon=""
      class="ml-2 pysepal-file-input-field"
      :error-messages="getErrorMessages"
      @update:model-value="setSelection"
    >
      <template v-slot:selection="{ index }">
        <v-chip v-if="index === 0" size="small" color="primary" variant="flat">
          {{ countLabel }}
        </v-chip>
      </template>
      <template v-slot:item="{ item, props }">
        <v-list-item v-bind="props">
          <template v-slot:title>
            <span :title="item.raw">{{ item.raw }}</span>
          </template>
          <template v-slot:append>
            <v-icon size="small" title="Remove">class:fa-solid fa-times</v-icon>
          </template>
        </v-list-item>
      </template>
      <template v-slot:append-inner>
        <v-btn
          v-if="clearable"
          icon
          variant="text"
          density="comfortable"
          color="primary"
          @click.stop="reset"
          @mousedown.stop
          @mouseup.stop
        >
          <v-icon>class:fa-solid fa-times</v-icon>
        </v-btn>
        <v-btn
          icon
          variant="text"
          density="comfortable"
          color="primary"
          @click.stop="reloadFiles"
          @mousedown.stop
          @mouseup.stop
        >
          <v-icon>class:fa-solid fa-sync-alt</v-icon>
        </v-btn>
      </template>
    </v-select>
  </v-row>
</template>

<script>
module.exports = {
  name: "FileInput",

  // The widget's synced traits (file_list, value, root...) arrive as data. Declaring
  // them as props too would make the template read the unset props instead.

  data() {
    return {
      showFileMenu: false,
      searchQuery: "",
      selectedIndex: null,
      isKeyboardNavigation: false,
      enteredFolderAt: 0,
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

    selectedPaths() {
      return this.multiple && Array.isArray(this.value) ? this.value : [];
    },

    countLabel() {
      const count = this.selectedPaths.length;
      if (!count) return "";
      const [one, many] = this.select_folders
        ? ["item", "items"]
        : ["file", "files"];
      return count === 1 ? `1 ${one}` : `${count} ${many}`;
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
      this.value = this.multiple ? [] : "";
      this.error_messages = [];
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
        this.enteredFolderAt = Date.now();
        // Clear search and selection, refocus
        this.searchQuery = "";
        this.selectedIndex = null;
        this.focusSearchField();
      } else if (this.multiple) {
        // The second click of a double click on a folder can land on the
        // listing that replaced it; it must not pick a file there.
        const recent = Date.now() - this.enteredFolderAt < 400;
        if (recent && !this.isKeyboardNavigation) return;
        this.toggleFile(this.fullPath(item));
      } else {
        // File selected - set value and close menu
        this.value = this.fullPath(item);
        this.showFileMenu = false;
      }
    },

    fullPath(item) {
      return this.base_path ? this.base_path + "/" + item.path : item.path;
    },

    isCheckable(item) {
      if (!this.multiple) return false;
      if (item.type === "file") return true;
      return this.select_folders && item.name !== "..";
    },

    isSelected(item) {
      return (
        this.isCheckable(item) &&
        this.selectedPaths.includes(this.fullPath(item))
      );
    },

    // Assign a new array: Python only sees a replaced value, not a mutated one.
    setSelection(paths) {
      this.value = [...paths];
    },

    toggleFile(path) {
      this.setSelection(
        this.selectedPaths.includes(path)
          ? this.selectedPaths.filter((p) => p !== path)
          : [...this.selectedPaths, path]
      );
    },

    getItemStyle(index) {
      if (this.selectedIndex === index) {
        return {
          backgroundColor: "rgba(25, 118, 210, 0.16)",
          borderLeft: "3px solid rgb(var(--v-theme-primary))",
        };
      }
      return {};
    },

    getTitleStyle(index) {
      if (this.selectedIndex === index) {
        return {
          fontWeight: 600,
          color: "rgb(var(--v-theme-primary))",
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
        "": { color: "primary-contrast", icon: "fa-regular fa-folder" },
        ".csv": { color: "secondary-contrast", icon: "fa-solid fa-table" },
        ".txt": { color: "secondary-contrast", icon: "fa-solid fa-table" },
        ".tif": { color: "secondary-contrast", icon: "fa-regular fa-image" },
        ".tiff": { color: "secondary-contrast", icon: "fa-regular fa-image" },
        ".png": { color: "secondary-contrast", icon: "fa-regular fa-image" },
        ".vrt": { color: "secondary-contrast", icon: "fa-regular fa-image" },
        ".shp": {
          color: "secondary-contrast",
          icon: "fa-solid fa-vector-square",
        },
        ".ipynb": { color: "green", icon: "fa-regular fa-file-code" },
        ".py": { color: "secondary-contrast", icon: "fa-regular fa-file-code" },
        ".json": {
          color: "secondary-contrast",
          icon: "fa-regular fa-file-code",
        },
        ".geojson": {
          color: "secondary-contrast",
          icon: "fa-solid fa-vector-square",
        },
        ".gpkg": {
          color: "secondary-contrast",
          icon: "fa-solid fa-vector-square",
        },
        ".pdf": { color: "secondary-contrast", icon: "fa-regular fa-file-pdf" },
        ".zip": {
          color: "secondary-contrast",
          icon: "fa-regular fa-file-archive",
        },
        ".log": { color: "secondary-contrast", icon: "fa-regular fa-file-alt" },
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
/* Not scoped: ipyvuetify drops a scoped style block from a runtime template. */
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
  .pysepal-file-input-btn .v-icon.v-icon--start {
    margin-inline: 0 !important;
  }
}
@container pysepal-file-input (max-width: 300px) {
  .pysepal-file-input-field {
    display: none !important;
  }
}

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
  line-height: 1rem;
}

.pysepal-file-input-crumb {
  cursor: pointer;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.pysepal-file-input-crumb:hover:not(.v-breadcrumbs-item--disabled) {
  text-decoration: underline;
}

.pysepal-file-input-item--active {
  transition: background-color 120ms ease, border-left 120ms ease;
}

.pysepal-file-input-item__title--active {
  transition: color 120ms ease;
}

/* 48px rows (default density), dense titles, caption-sized file size */
.pysepal-file-input-list .v-list-item-title {
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1rem;
}
/* A flat list: no hover or active overlay on the rows */
.pysepal-file-input-list .v-list-item__overlay {
  display: none;
}
.pysepal-file-input-size {
  font-size: 0.75rem;
  opacity: var(--v-medium-emphasis-opacity);
}

.pysepal-file-input-check {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  cursor: pointer;
}
/* The circle takes the text colour, so it follows the theme: primary when on */
.pysepal-file-input-check::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: currentColor;
  opacity: 0;
  transition: opacity 0.1s;
}
.pysepal-file-input-check:hover::before {
  opacity: 0.08;
}
.pysepal-file-input-check--on::before {
  opacity: 0.16;
}
.pysepal-file-input-check .v-icon {
  position: relative;
  opacity: 0.35;
  transition: transform 0.1s, opacity 0.1s;
}
.pysepal-file-input-check--on .v-icon {
  opacity: 1;
  transform: scale(1.2);
}
</style>
