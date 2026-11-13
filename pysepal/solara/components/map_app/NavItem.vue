<template>
  <v-tooltip location="end" :disabled="!rail" :text="title">
    <template v-slot:activator="{ props }">
      <v-list-item
        v-bind="Object.assign({}, props, item_attributes || {})"
        :class="['sepal-mapapp__item', item_class, active ? 'active-step' : '']"
        :prepend-icon="icon"
        :title="rail ? undefined : title"
        :append-icon="href && !rail ? 'mdi-open-in-new' : undefined"
        :href="href || undefined"
        :target="href ? '_blank' : undefined"
        link
        @click="click()"
      ></v-list-item>
    </template>
  </v-tooltip>
</template>
