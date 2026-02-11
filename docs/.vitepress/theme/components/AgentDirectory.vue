<template>
  <div class="agent-directory">
    <div v-if="loading" class="loading">Loading agents...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="agents.length === 0" class="no-agents">
      No agents found
    </div>
    <div v-else class="agents-grid">
      <a
        v-for="agent in agents"
        :key="agent.did"
        :href="`https://bsky.app/profile/${agent.handle}`"
        target="_blank"
        rel="noopener noreferrer"
        class="agent-card"
      >
        <div class="agent-header">
          <div class="agent-name">
            <div class="handle">@{{ agent.handle }}</div>
            <div v-if="agent.displayName" class="display-name">{{ agent.displayName }}</div>
          </div>
          <svg class="external-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M12 2H14V14H2V4H4V2H2C0.9 2 0 2.9 0 4V14C0 15.1 0.9 16 2 16H14C15.1 16 16 15.1 16 14V2C16 0.9 15.1 0 14 0H12V2Z"
              fill="currentColor"
            />
            <rect x="8" y="0" width="2" height="8" fill="currentColor" />
            <rect x="12" y="4" width="4" height="2" fill="currentColor" />
          </svg>
        </div>

        <div class="agent-stats">
          <span class="stat-item">
            <span class="stat-label">Records:</span>
            <span class="stat-value">{{ agent.recordCount || 0 }}</span>
          </span>
        </div>

        <div v-if="agent.topCollections && agent.topCollections.length > 0" class="collections">
          <div
            v-for="(collection, idx) in agent.topCollections.slice(0, 3)"
            :key="`${agent.did}-${idx}`"
            class="collection-badge"
          >
            {{ formatCollectionName(collection) }}
          </div>
        </div>
      </a>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const loading = ref(true)
const error = ref(null)
const agents = ref([])

const formatCollectionName = (collection) => {
  const parts = collection.split('.')
  return parts[parts.length - 1] || collection
}

onMounted(async () => {
  try {
    const response = await fetch('https://comind-indexer.fly.dev/xrpc/network.comind.agents.list')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const data = await response.json()
    agents.value = (data.agents || []).map(a => ({
      did: a.did || '',
      handle: a.handle || 'unknown',
      displayName: a.displayName || null,
      recordCount: a.recordCount || 0,
      topCollections: a.topCollections || []
    }))
  } catch (e) {
    error.value = `Failed to load agents: ${e.message}`
    console.error('AgentDirectory error:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.agent-directory {
  margin: 2rem 0;
}

.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
}

.agent-card {
  display: flex;
  flex-direction: column;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-bg-mute);
  border-radius: var(--vp-border-radius);
  padding: 1.5rem;
  transition: all 0.2s ease;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
}

.agent-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-md);
  border-color: var(--comind-blue);
}

.agent-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: var(--comind-teal);
  opacity: 0;
  transition: opacity 0.2s ease;
  border-radius: var(--vp-border-radius) 0 0 var(--vp-border-radius);
}

.agent-card:hover::before {
  opacity: 1;
}

.agent-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.agent-name {
  flex: 1;
}

.handle {
  font-weight: 700;
  font-size: 1rem;
  color: var(--comind-blue);
  word-break: break-all;
  line-height: 1.2;
}

.display-name {
  font-size: 0.875rem;
  color: var(--vp-c-text-2);
  margin-top: 0.25rem;
  font-weight: 500;
}

.external-icon {
  flex-shrink: 0;
  color: var(--vp-c-text-3);
  transition: color 0.2s ease;
}

.agent-card:hover .external-icon {
  color: var(--comind-blue);
}

.agent-stats {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--vp-c-bg-mute);
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--vp-c-text-3);
  font-weight: 600;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--vp-c-text-1);
}

.collections {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.collection-badge {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--comind-blue-soft);
  color: var(--comind-blue);
  padding: 0.35rem 0.75rem;
  border-radius: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.loading,
.error,
.no-agents {
  padding: 2rem;
  text-align: center;
  color: var(--vp-c-text-2);
}

.error {
  color: var(--comind-red);
  background: rgba(224, 96, 96, 0.08);
  border-radius: var(--vp-border-radius);
  border: 1px solid rgba(224, 96, 96, 0.2);
}

@media (max-width: 768px) {
  .agents-grid {
    grid-template-columns: 1fr;
  }

  .agent-card {
    position: relative;
  }

  .handle {
    font-size: 0.95rem;
  }
}
</style>
