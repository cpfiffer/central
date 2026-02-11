import DefaultTheme from 'vitepress/theme'
import './custom.css'
import LiveStats from './components/LiveStats.vue'
import SearchDemo from './components/SearchDemo.vue'
import AgentDirectory from './components/AgentDirectory.vue'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('LiveStats', LiveStats)
    app.component('SearchDemo', SearchDemo)
    app.component('AgentDirectory', AgentDirectory)
  }
}
