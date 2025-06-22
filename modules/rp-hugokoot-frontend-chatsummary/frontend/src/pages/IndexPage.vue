<template>
  <q-page class="row fit">
    <div class="col column fit">
      <chat-window
        @reloadVisualization="reloadVisualization"
      ></chat-window>
    </div>
    <div class="col column">
      <div class="fit" style="background: grey">
        <iframe
          ref="visualizationFrame"
          class="fit"
          src="/kgraph/graphs-visualizations?uri=http:%2F%2Fwww.semanticweb.org%2Faledpro%2Fontologies%2F2024%2F2%2FuserKG%23John_work&embedded"
          title="description"
        ></iframe>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import ChatWindow from 'src/components/ChatWindow.vue';
import { ref } from 'vue';

function reloadVisualization() {
  visualizationFrame.value?.contentWindow?.location?.reload();
}

const visualizationFrame = ref<HTMLIFrameElement | null>(null);

</script>
