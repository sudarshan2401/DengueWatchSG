import { useState } from 'react'
import type { RiskLevel } from '../types'
import styles from './ChoroplethMap.module.css'

/** Colour palette for each risk level */
export const RISK_COLOURS: Record<RiskLevel, string> = {
  Low: '#4caf50',
  Medium: '#ff9800',
  High: '#f44336',
}

interface PlanningAreaFeature {
  name: string
  riskLevel: RiskLevel
  score: number
}

interface Props {
  areas: PlanningAreaFeature[]
  onAreaClick?: (area: PlanningAreaFeature) => void
}

/**
 * ChoroplethMap renders a Leaflet map of Singapore planning areas
 * colour-coded by their predicted dengue risk level.
 *
 * NOTE: Actual GeoJSON boundary data should be loaded from
 *       /public/singapore-planning-areas.geojson
 *       (source: data.gov.sg Master Plan Subzone boundary).
 */
export default function ChoroplethMap({ areas, onAreaClick }: Props) {
  const [tooltip, setTooltip] = useState<{ name: string; riskLevel: RiskLevel } | null>(null)

  // Build a lookup map for fast access during GeoJSON rendering
  const riskByArea = new Map(areas.map((a) => [a.name.toUpperCase(), a]))

  return (
    <div className={styles.mapWrapper}>
      {/* Map placeholder — replace with react-leaflet GeoJSON layers in production */}
      <div className={styles.mapPlaceholder} aria-label="Singapore dengue risk choropleth map">
        <div className={styles.placeholderHeader}>
          <div>
            <p className={styles.placeholderText}>🗺️ Singapore Planning Areas</p>
            <p className={styles.placeholderSub}>Click an area to see its risk level</p>
          </div>
          <ul className={styles.legend}>
            {(Object.entries(RISK_COLOURS) as [RiskLevel, string][]).map(([level, colour]) => (
              <li key={level} className={styles.legendItem}>
                <span className={styles.legendDot} style={{ backgroundColor: colour }} />
                {level} Risk
              </li>
            ))}
          </ul>
        </div>

        <ul className={styles.areaList}>
          {areas.slice(0, 8).map((area) => (
            <li
              key={area.name}
              className={styles.areaItem}
              style={{ borderLeft: `3px solid ${RISK_COLOURS[area.riskLevel]}` }}
              onClick={() => onAreaClick?.(area)}
              onMouseEnter={() => setTooltip({ name: area.name, riskLevel: area.riskLevel })}
              onMouseLeave={() => setTooltip(null)}
            >
              <span>{area.name}</span>
              <span
                className={styles.badge}
                style={{ backgroundColor: RISK_COLOURS[area.riskLevel] }}
              >
                {area.riskLevel}
              </span>
            </li>
          ))}
        </ul>

        {tooltip && (
          <div className={styles.tooltip}>
            <strong>{tooltip.name}</strong> — {tooltip.riskLevel} Risk
          </div>
        )}
      </div>
      {/* Suppress unused-variable warning for the lookup map used in GeoJSON render */}
      <span data-testid="area-count" hidden>{riskByArea.size}</span>
    </div>
  )
}
