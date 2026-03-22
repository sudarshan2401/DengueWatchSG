import { useEffect, useState, useCallback, useMemo } from 'react'
import { getRiskMap } from '../api'
import type { PlanningAreaRisk, PostalCodeInfo } from '../types'
import ChoroplethMap from '../components/ChoroplethMap'
import PostalCodeSearch from '../components/PostalCodeSearch'
import NotificationBell from '../components/NotificationBell'
import logo from '../assets/logo.png'
import styles from './LandingPage.module.css'

export default function LandingPage() {
  const [areas, setAreas] = useState<PlanningAreaRisk[]>([])
  const [selectedArea, setSelectedArea] = useState<PostalCodeInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const riskByArea = useMemo(
    () => new Map(areas.map((a) => [a.planningArea.toUpperCase(), a.riskLevel])),
    [areas],
  )

  const loadData = useCallback(() => {
    setLoading(true)
    setError(null)
    getRiskMap()
      .then(setAreas)
      .catch(() => setError('Failed to load risk map data. Please check your connection and try again.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadData() }, [loadData])

  return (
    <div className={styles.page}>
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <img src={logo} alt="DengueWatch SG" className={styles.logoImage} />
          <div>
            <span className={styles.logoName}>DengueWatch</span>
            <span className={styles.logoSuffix}> SG</span>
          </div>
        </div>
        <NotificationBell />
      </header>

      {/* ── Main content ─────────────────────────────────────────────── */}
      <main className={styles.main}>
        <section className={styles.intro}>
          <h2 className={styles.introHeading}>Singapore Dengue Risk Map</h2>
          <p className={styles.introText}>
            Weekly predicted dengue risk for each planning area, powered by an XGBoost
            model trained on historical case counts and weather data.
          </p>
        </section>

        <div className={styles.searchBar}>
          <PostalCodeSearch onResult={(info) => setSelectedArea(info)} riskByArea={riskByArea} />
        </div>


        {/* Map */}
        <div className={styles.mapContainer}>
          {loading && (
            <div className={styles.loadingState}>
              <div className={styles.spinner} />
              <p className={styles.loadingText}>Fetching Singapore risk data&hellip;</p>
            </div>
          )}
          {error && !loading && (
            <div className={styles.errorState}>
              <div className={styles.errorIcon}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
              <h3 className={styles.errorTitle}>Unable to load map</h3>
              <p className={styles.errorBody}>{error}</p>
              <button className={styles.retryBtn} onClick={loadData}>
                Try again
              </button>
            </div>
          )}
          {!loading && !error && (
            <ChoroplethMap
              areas={areas.map((a) => ({
                name: a.planningArea,
                riskLevel: a.riskLevel,
                score: a.score,
                latitude: a.latitude,
                longitude: a.longitude,
              }))}
              selectedArea={selectedArea?.planningArea}
              pinCoords={selectedArea ? [selectedArea.latitude, selectedArea.longitude] : undefined}
            />
          )}
        </div>
      </main>

      <footer className={styles.footer}>
        <p>Data sourced from NEA &amp; data.gov.sg &middot; Updated weekly</p>
      </footer>
    </div>
  )
}
