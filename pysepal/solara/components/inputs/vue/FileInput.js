module.exports = {
  name: "FileInput",

  // The widget's synced traits (file_list, value, root...) arrive as data. Declaring
  // them as props too would make the Vue 3 template read the unset props instead.

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

    isVuetify3() {
      return !!(
        this.$vuetify &&
        this.$vuetify.theme &&
        this.$vuetify.theme.global
      );
    },

    primaryColor() {
      return this.isVuetify3
        ? "rgb(var(--v-theme-primary))"
        : "var(--v-primary-base, #1976d2)";
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
          borderLeft: `3px solid ${this.primaryColor}`,
        };
      }
      return {};
    },

    getTitleStyle(index) {
      if (this.selectedIndex === index) {
        return {
          fontWeight: 600,
          color: this.primaryColor,
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
      const color = this.getFileMetadata(item).color;
      // Vuetify 3 names the custom theme colours with dashes: primary-contrast
      return this.isVuetify3 ? color.replace(/_/g, "-") : color;
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
