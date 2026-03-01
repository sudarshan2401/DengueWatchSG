import { BrowserRouter, Routes, Route } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import NotificationPage from './pages/NotificationPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/subscribe" element={<NotificationPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
