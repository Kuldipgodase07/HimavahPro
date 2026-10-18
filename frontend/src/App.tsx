import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { ToastProvider, PageSkeleton } from './components/ui'
import { RequireAuth, NAV } from './components/Layout'
import Landing from './pages/Landing'
import SignIn from './pages/SignIn'

const CommandCentre = lazy(() => import('./pages/CommandCentre'))
const LogisticsMap = lazy(() => import('./pages/LogisticsMap'))
const Forecasts = lazy(() => import('./pages/Forecasts'))
const Inventory = lazy(() => import('./pages/Inventory'))
const RoutesPage = lazy(() => import('./pages/RouteIntel'))
const Recommendations = lazy(() => import('./pages/Recommendations'))
const Simulator = lazy(() => import('./pages/Simulator'))
const Convoys = lazy(() => import('./pages/Convoys'))
const Field = lazy(() => import('./pages/Field'))
const ResponsibleAI = lazy(() => import('./pages/ResponsibleAI'))
const Governance = lazy(() => import('./pages/Governance'))
const Audit = lazy(() => import('./pages/Audit'))
const Reports = lazy(() => import('./pages/Reports'))
const Admin = lazy(() => import('./pages/Admin'))

function Home() {
  const { can } = useAuth()
  const first = NAV.find((n) => can(n.perm))
  return first && first.to !== '/app' ? <Navigate to={first.to} replace /> : <CommandCentre />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider><ToastProvider>
        <Suspense fallback={<div className="p-6"><PageSkeleton /></div>}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/signin" element={<SignIn />} />
            <Route path="/app" element={<RequireAuth />}>
              <Route index element={<Home />} />
              <Route path="map" element={<LogisticsMap />} />
              <Route path="forecasts" element={<Forecasts />} />
              <Route path="inventory" element={<Inventory />} />
              <Route path="routes" element={<RoutesPage />} />
              <Route path="recommendations" element={<Recommendations />} />
              <Route path="simulator" element={<Simulator />} />
              <Route path="convoys" element={<Convoys />} />
              <Route path="field" element={<Field />} />
              <Route path="responsible-ai" element={<ResponsibleAI />} />
              <Route path="governance" element={<Governance />} />
              <Route path="audit" element={<Audit />} />
              <Route path="reports" element={<Reports />} />
              <Route path="admin" element={<Admin />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </ToastProvider></AuthProvider>
    </BrowserRouter>
  )
}
