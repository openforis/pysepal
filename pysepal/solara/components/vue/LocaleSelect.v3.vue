<template>
  <div>
    <v-btn
      variant="flat"
      @click="openDialog"
      style="background-color: unset !important"
    >
      <v-icon size="small" start>mdi-translate</v-icon>
      {{ value }}
    </v-btn>

    <v-dialog v-model="dialogOpen" max-width="400">
      <v-card>
        <v-card-title
          class="text-h5 d-flex justify-space-between align-center pt-4 px-6 pb-2"
        >
          <span>Select your language</span>
          <v-btn
            icon
            variant="text"
            density="comfortable"
            class="text-medium-emphasis"
            @click="closeDialog"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text class="pt-0 pb-5">
          <v-list>
            <v-list-item
              v-for="(locale, index) in available_locales"
              :key="index"
              @click="selectLanguage(locale.code)"
            >
              <v-list-item-title
                >{{ locale.name }} ({{ locale.code }})</v-list-item-title
              >
              <!-- the append slot dims icons to medium emphasis -->
              <template v-if="isSelected(locale.code)" #append>
                <v-icon color="primary" style="opacity: 1">mdi-check</v-icon>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>
