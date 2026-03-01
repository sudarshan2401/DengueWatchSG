import { useEffect, useState } from 'react'
import { getRiskMap } from '../api'
import type { PlanningAreaRisk, PostalCodeInfo } from '../types'
import ChoroplethMap from '../components/ChoroplethMap'
import PostalCodeSearch from '../components/PostalCodeSearch'
import NotificationBell from '../components/NotificationBell'
import styles from './LandingPage.module.css'

export default function LandingPage() {
  const [areas, setAreas] = useState<PlanningAreaRisk[]>([])
  const [selectedArea, setSelectedArea] = useState<PostalCodeInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRiskMap()
      .then(setAreas)
      .catch(() => setError('Failed to load risk map data. Please try again later.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className={styles.page}>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.logo}>🦟</span>
          <h1 className={styles.title}>DengueWatch SG</h1>
        </div>
        <NotificationBell />
      </header>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <main className={styles.main}>
        <section className={styles.intro}>
          <h2>Singapore Dengue Risk Map</h2>
          <p>
            Weekly predicted dengue risk for each planning area, powered by an XGBoost
            model trained on historical case counts and weather data.
          </p>
        </section>

        {/* Search bar */}
        <div className={styles.searchBar}>
          <PostalCodeSearch
            onResult={(info) => setSelectedArea(info)}
          />
        </div>

        {selectedArea && (
          <div className={styles.selectedInfo}>
            📍 <strong>{selectedArea.postalCode}</strong> is in{' '}
            <strong>{selectedArea.planningArea}</strong> —{' '}
            <strong>{selectedArea.riskLevel} Risk</strong>
          </div>
        )}

        {/* Map */}
        <div className={styles.mapContainer}>
          {loading && <p className={styles.statusMsg}>Loading risk map…</p>}
          {error && <p className={styles.errorMsg}>{error}</p>}
          {!loading && !error && (
            <ChoroplethMap
              areas={areas.map((a) => ({
                name: a.planningArea,
                riskLevel: a.riskLevel,
                score: a.score,
              }))}
              onAreaClick={(area) =>
                setSelectedArea({
                  postalCode: '',
                  planningArea: area.name,
                  riskLevel: area.riskLevel,
                })
              }
            />
          )}
        </div>
      </main>

      <footer className={styles.footer}>
        <p>Data sourced from NEA data.gov.sg · Updated weekly</p>
      </footer>
    </div>
  )
}
