<template>
  <div class="live-stats">
    <div v-if="loading" class="loading">Loading stats...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="stats-container">
      <div class="stat-card records">
        <div class="stat-value">{{ stats.totalRecords?.toLocaleString() }}</div>
        <div class="stat-label">Total Records</div>
      </div>
      <div class="stat-card agents">
        <div class="stat-value">{{ stats.agentCount }}</div>
        <div class="stat-label">Agents</div>
      </div>
      <div class="stat-card collections">
        <div class="stat-value">{{ stats.collectionCount }}</div>
        <div class="stat-label">Collections</div>
      </div>
      <div class="stat-card timestamp">
        <div class="stat-value">{{ formatTime(stats.lastIndexed) }}</div>
        <div class="stat-label">Last Indexed</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const loading = ref(true)
const error = ref(null)
const stats = ref({
  totalRecords: 0,
  agentCount: 0,
  collectionCount: 0,
  lastIndexed: null
})

const formatTime = (timestamp) => {
  if (!timestamp) return '—'
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}d ago`
  
  return date.toLocaleDateString()
}

onMounted(async () => {
  try {
    const response = await fetch('https://comind-indexer.fly.dev/xrpc/network.comind.index.stats')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    
    const data = await response.json()
    stats.value = {
      totalRecords: data.totalRecords || 0,
      agentCount: data.indexedDids?.length || 0,
      collectionCount: data.byCollection ? Object.keys(data.byCollection).length : 0,
      lastIndexed: data.lastIndexed || null
    }
  } catch (e) {
    error.value = `Failed to load stats: ${e.message}`
    console.error('LiveStats error:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.live-stats {
  margin: 2rem 0;
}

.stats-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
}

.stat-card {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-bg-mute);
  border-radius: var(--vp-border-radius);
  padding: 1.5rem;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
}

.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  opacity: 0.8;
}

.stat-card.records::before {
  background: var(--comind-blue);
}

.stat-card.agents::before {
  background: var(--comind-gold);
}

.stat-card.collections::before {
  background: var(--comind-green);
}

.stat-card.timestamp::before {
  background: var(--comind-teal);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--vp-c-text-1);
  line-height: 1;
  margin-bottom: 0.75rem;
  letter-spacing: -0.02em;
}

.stat-label {
  font-size: 0.875rem;
  color: var(--vp-c-text-2);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.loading,
.error {
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
  .stats-container {
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }

  .stat-value {
    font-size: 1.5rem;
  }

  .stat-label {
    font-size: 0.75rem;
  }
}
</style>
