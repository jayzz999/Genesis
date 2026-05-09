import { useState } from 'react'
import GenesisPage from './components/genesis/GenesisPage'
import GenesisLanding from './components/landing/GenesisLanding'

function shouldOpenApp() {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  return params.get('app') === '1' || window.location.hash === '#app'
}

export default function App() {
  const [showApp, setShowApp] = useState(shouldOpenApp)

  if (showApp) {
    return <GenesisPage />
  }

  return (
    <GenesisLanding
      onEnter={() => {
        window.history.replaceState(null, '', '#app')
        setShowApp(true)
      }}
    />
  )
}
