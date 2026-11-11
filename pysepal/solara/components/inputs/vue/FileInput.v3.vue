<!-- Vuetify 3 gives an unprefixed icon the mdi class and font; class: renders Font Awesome as is -->
<template>
  <v-row class="d-flex align-center mx-2 my-0 pysepal-file-input-root">
    <!-- width, not min-width: Vuetify 3 caps a menu's min-width at its activator's width -->
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
              <!-- title is a Vuetify 3 prop (the label), so the tooltip goes on a span -->
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

/* The Vuetify 2 look: 48px rows (default density), dense titles, caption-sized file size */
.pysepal-file-input-list .v-list-item-title {
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1rem;
}
/* Vuetify 2's flat list: no hover or active overlay on the rows */
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
