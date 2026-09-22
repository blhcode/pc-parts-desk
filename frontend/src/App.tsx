import { useState } from 'react'
import { Inbox } from './Inbox'
import { TitleScreen } from './TitleScreen'
import './index.css'

export default function App() {
  const [saveId, setSaveId] = useState<string | null>(null)

  return (
    <div className="app-shell">
      {saveId ? (
        <Inbox onExit={() => setSaveId(null)} />
      ) : (
        <TitleScreen onLoad={(id) => setSaveId(id)} />
      )}
    </div>
  )
}
