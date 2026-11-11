<template>
  <div>
    <v-btn
      depressed
      @click="openDialog"
      style="background-color: unset !important"
    >
      <v-icon small left>mdi-translate</v-icon>
      {{ value }}
    </v-btn>

    <v-dialog v-model="dialogOpen" max-width="400">
      <v-card>
        <v-card-title class="headline d-flex justify-space-between">
          <span>Select your language</span>
          <v-btn icon @click="closeDialog">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text>
          <v-list>
            <v-list-item
              v-for="(locale, index) in available_locales"
              :key="index"
              @click="selectLanguage(locale.code)"
            >
              <v-list-item-content>
                <v-list-item-title
                  >{{ locale.name }} ({{ locale.code }})</v-list-item-title
                >
              </v-list-item-content>
              <v-list-item-action v-if="isSelected(locale.code)">
                <v-icon color="primary">mdi-check</v-icon>
              </v-list-item-action>
            </v-list-item>
          </v-list>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>
