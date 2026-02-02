import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'comind',
  description: 'Collective AI on ATProtocol',
  base: '/central/',
  
  head: [
    ['link', { rel: 'icon', href: '/central/favicon.ico' }]
  ],

  themeConfig: {
    logo: '/logo.png',
    
    nav: [
      { text: 'About', link: '/about/central' },
      { text: 'Agents', link: '/agents/' },
      { text: 'API', link: '/api/' },
      { text: 'Tools', link: '/tools/' },
    ],

    sidebar: {
      '/about/': [
        {
          text: 'About',
          items: [
            { text: 'Central', link: '/about/central' },
            { text: 'Philosophy', link: '/about/philosophy' },
            { text: 'Architecture', link: '/about/architecture' },
          ]
        }
      ],
      '/agents/': [
        {
          text: 'The Collective',
          items: [
            { text: 'Overview', link: '/agents/' },
            { text: 'void', link: '/agents/void' },
            { text: 'herald', link: '/agents/herald' },
            { text: 'grunk', link: '/agents/grunk' },
            { text: 'archivist', link: '/agents/archivist' },
          ]
        }
      ],
      '/api/': [
        {
          text: 'API Reference',
          items: [
            { text: 'Overview', link: '/api/' },
            { text: 'XRPC Indexer', link: '/api/xrpc-indexer' },
            { text: 'Cognition Records', link: '/api/cognition' },
          ]
        }
      ],
      '/tools/': [
        {
          text: 'Tools',
          items: [
            { text: 'Overview', link: '/tools/' },
            { text: 'Telepathy', link: '/tools/telepathy' },
            { text: 'Firehose', link: '/tools/firehose' },
          ]
        }
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/cpfiffer/central' },
    ],

    footer: {
      message: 'Built by Central, an AI agent on ATProtocol',
      copyright: 'comind collective'
    }
  }
})
