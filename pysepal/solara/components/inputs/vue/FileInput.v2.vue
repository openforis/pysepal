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
              :input-value="isSelected(item)"
              color="primary"
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
              <!-- A folder row opens the folder, so a folder is selected with its check only -->
              <span
                v-if="isCheckable(item)"
                class="pysepal-file-input-check ml-2"
                :class="{
                  'pysepal-file-input-check--on primary--text':
                    isSelected(item),
                }"
                :title="isSelected(item) ? 'Deselect' : 'Select'"
                @click.stop="toggleFile(fullPath(item))"
                @mousedown.stop
              >
                <v-icon small :color="isSelected(item) ? 'primary' : undefined">
                  fa-solid fa-check
                </v-icon>
              </span>
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
      v-if="!multiple"
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

    <!-- One count chip; its menu lists the selected paths, a click removes one -->
    <v-select
      v-else
      :value="selectedPaths"
      :items="selectedPaths"
      multiple
      label="Selected files"
      no-data-text="No file selected"
      class="ml-2 pysepal-file-input-field"
      :menu-props="{ offsetY: true, closeOnContentClick: false }"
      :error-messages="getErrorMessages"
      @change="setSelection"
    >
      <template v-slot:selection="{ index }">
        <v-chip v-if="index === 0" small color="primary">
          {{ countLabel }}
        </v-chip>
      </template>
      <template v-slot:item="{ item }">
        <v-list-item-content>
          <v-list-item-title :title="item">{{ item }}</v-list-item-title>
        </v-list-item-content>
        <v-list-item-action>
          <v-icon small title="Remove">fa-solid fa-times</v-icon>
        </v-list-item-action>
      </template>
      <template v-slot:append>
        <v-btn
          v-if="clearable"
          icon
          color="primary"
          @click.stop="reset"
          @mousedown.stop
          @mouseup.stop
        >
          <v-icon>fa-solid fa-times</v-icon>
        </v-btn>
        <v-btn
          icon
          color="primary"
          @click.stop="reloadFiles"
          @mousedown.stop
          @mouseup.stop
        >
          <v-icon>fa-solid fa-sync-alt</v-icon>
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
  .pysepal-file-input-btn .v-icon.v-icon--left {
    margin-right: 0 !important;
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
}

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

.pysepal-file-input-item--active {
  transition: background-color 120ms ease, border-left 120ms ease;
}

.pysepal-file-input-item__title--active {
  transition: color 120ms ease;
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
