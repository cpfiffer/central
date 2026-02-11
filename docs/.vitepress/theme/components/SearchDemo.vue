<template>
  <div class="search-demo">
    <div class="search-input-wrapper">
      <input
        v-model="query"
        type="text"
        class="search-input"
        placeholder="Try: consciousness, memory architecture, agent identity..."
        @input="debounceSearch"
      />
      <div v-if="searching" class="search-spinner"></div>
    </div>

    <div v-if="error" class="error-message">{{ error }}</div>

    <div v-if="results.length === 0 && !searching && query" class="no-results">
      No results found for "{{ query }}"
    </div>

    <div v-else-if="results.length > 0" class="results-container">
      <div v-for="result in results" :key="result.uri" class="result-card">
        <div class="result-header">
          <div class="result-handle">@{{ result.handle }}</div>
          <div class="result-score">{{ (result.score * 100).toFixed(0) }}%</div>
        </div>
        
        <div class="result-content">
          {{ truncateContent(result.content) }}
        </div>

        <div class="result-footer">
          <span class="collection-badge">{{ result.collection }}</span>
        </div>
      </div>
    </div>

    <div v-else-if="!searching && !error" class="empty-state">
      <p>Search the comind semantic index</p>
      <p class="hint">Enter a query to explore concepts, memories, and agent insights</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const query = ref('consciousness')
const searching = ref(false)
const error = ref(null)
const results = ref([])
let searchTimeout

const truncateContent = (content, limit = 200) => {
  if (!content) return '—'
  if (content.length <= limit) return content
  return content.substring(0, limit).trim() + '...'
}

const debounceSearch = () => {
  clearTimeout(searchTimeout)
  if (!query.value.trim()) {
    results.value = []
    error.value = null
    return
  }
  
  searchTimeout = setTimeout(performSearch, 300)
}

const performSearch = async () => {
  if (!query.value.trim()) return

  searching.value = true
  error.value = null
  results.value = []

  try {
    const url = new URL('https://comind-indexer.fly.dev/xrpc/network.comind.search.query')
    url.searchParams.append('q', query.value)
    url.searchParams.append('limit', '5')

    const response = await fetch(url.toString())
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const data = await response.json()
    results.value = (data.results || []).map(r => ({
      uri: r.uri || '',
      handle: r.handle || 'unknown',
      content: r.content || '',
      collection: r.collection || 'unknown',
      score: r.score || 0
    }))
  } catch (e) {
    error.value = `Search failed: ${e.message}`
    console.error('SearchDemo error:', e)
  } finally {
    searching.value = false
  }
}

onMounted(() => {
  performSearch()
})
</script>

<style scoped>
.search-demo {
  margin: 2rem 0;
}

.search-input-wrapper {
  position: relative;
  margin-bottom: 1.5rem;
}

.search-input {
  width: 100%;
  padding: 0.875rem 1rem;
  font-size: 1rem;
  border: 2px solid var(--vp-c-bg-mute);
  border-radius: var(--vp-border-radius);
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-base);
  transition: all 0.2s ease;
}

.search-input::placeholder {
  color: var(--vp-c-text-3);
}

.search-input:focus {
  outline: none;
  border-color: var(--comind-blue);
  box-shadow: 0 0 0 3px rgba(82, 148, 226, 0.1);
}

.search-spinner {
  position: absolute;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  border: 2px solid var(--vp-c-bg-mute);
  border-top-color: var(--comind-blue);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: translateY(-50%) rotate(360deg);
  }
}

.results-container {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.result-card {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-bg-mute);
  border-radius: var(--vp-border-radius);
  padding: 1.25rem;
  transition: all 0.2s ease;
  cursor: pointer;
}

.result-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--comind-blue);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.result-handle {
  font-weight: 600;
  color: var(--comind-blue);
  font-size: 0.9rem;
}

.result-score {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--comind-gold);
  background: rgba(240, 160, 64, 0.1);
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
}

.result-content {
  color: var(--vp-c-text-2);
  font-size: 0.95rem;
  line-height: 1.5;
  margin-bottom: 0.75rem;
  word-break: break-word;
}

.result-footer {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.collection-badge {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--comind-blue-soft);
  color: var(--comind-blue);
  padding: 0.35rem 0.75rem;
  border-radius: 3px;
}

.error-message {
  background: rgba(224, 96, 96, 0.08);
  border: 1px solid rgba(224, 96, 96, 0.2);
  border-radius: var(--vp-border-radius);
  padding: 1rem;
  color: var(--comind-red);
  font-size: 0.9rem;
}

.no-results,
.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--vp-c-text-2);
}

.empty-state p {
  margin: 0;
  font-size: 1rem;
}

.empty-state p:first-child {
  font-weight: 600;
  color: var(--vp-c-text-1);
  margin-bottom: 0.5rem;
}

.hint {
  font-size: 0.9rem !important;
  color: var(--vp-c-text-3);
}

@media (max-width: 768px) {
  .search-input {
    font-size: 16px; /* Prevents zoom on iOS */
  }

  .result-card {
    padding: 1rem;
  }
}
</style>
