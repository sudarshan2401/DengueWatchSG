import { BrowserRouter, Routes, Route } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import NotificationPage from './pages/NotificationPage'
import UnsubscribePage from './pages/UnsubscribePage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/subscribe" element={<NotificationPage />} />
        <Route path="/unsubscribe" element={<UnsubscribePage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
