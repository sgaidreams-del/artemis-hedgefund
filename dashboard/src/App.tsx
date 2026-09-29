import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import ConnectionBar from './components/ConnectionBar'
import KillSwitch from './components/KillSwitch'
import Overview from './pages/Overview'
import TradeHistory from './pages/TradeHistory'
import Learnings from './pages/Learnings'
import CalendarPage from './pages/CalendarPage'
import OptionsPage from './pages/OptionsPage'
import SimulatorPage from './pages/SimulatorPage'

const tabs = [
  { to: '/', label: 'Overview' },
  { to: '/trades', label: 'Trade History' },
  { to: '/learnings', label: 'Learnings' },
  { to: '/options', label: 'Options' },
  { to: '/calendar', label: 'Calendar' },
  { to: '/simulator', label: 'Simulator' },
]

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <ConnectionBar />
        <header className="px-6 pt-4 pb-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-lg font-bold">Artemis</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)' }}>
              paper
            </span>
            <KillSwitch />
          </div>
          <nav className="flex gap-1">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.to === '/'}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-full text-sm transition-colors ${isActive ? '' : ''}`
                }
                style={({ isActive }) => ({
                  backgroundColor: isActive ? 'var(--color-surface-hover)' : 'transparent',
                  color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                })}
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
        </header>
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/trades" element={<TradeHistory />} />
            <Route path="/learnings" element={<Learnings />} />
            <Route path="/options" element={<OptionsPage />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/simulator" element={<SimulatorPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
