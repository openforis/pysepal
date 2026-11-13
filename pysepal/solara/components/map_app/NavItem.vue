<template>
  <v-tooltip right :disabled="!rail">
    <template v-slot:activator="{ on }">
      <v-list-item
        v-bind="item_attributes || {}"
        v-on="on"
        :class="['sepal-mapapp__item', item_class, active ? 'active-step' : '']"
        :href="href || undefined"
        :target="href ? '_blank' : undefined"
        link
        @click="click()"
      >
        <v-list-item-icon>
          <v-icon class="mb-1">{{ icon }}</v-icon>
        </v-list-item-icon>
        <v-list-item-content v-if="!rail">
          <v-list-item-title class="font-weight-medium d-flex align-center">
            {{ title }}
            <template v-if="href">
              <v-spacer></v-spacer>
              <v-icon class="ml-1" small>mdi-open-in-new</v-icon>
            </template>
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
    <span>{{ title }}</span>
  </v-tooltip>
</template>
