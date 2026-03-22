import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, GeoJSON, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { GeoJSON as LeafletGeoJSON } from 'leaflet'
import type { GeoJsonObject, Feature } from 'geojson'
import type { Layer } from 'leaflet'

const pinIcon = L.divIcon({
  className: '',
  html: `<div style="
    width:18px;height:18px;
    background:#1976d2;
    border:3px solid #fff;
    border-radius:50% 50% 50% 0;
    transform:rotate(-45deg);
    box-shadow:0 2px 6px rgba(0,0,0,0.4);
  "></div>`,
  iconSize: [18, 18],
  iconAnchor: [9, 18],
  popupAnchor: [0, -20],
})
import type { RiskLevel } from '../types'
import { getPlanningAreaBoundaries } from '../api'
import styles from './ChoroplethMap.module.css'

export const RISK_COLOURS: Record<RiskLevel, string> = {
  Low: '#4caf50',
  Medium: '#ff9800',
  High: '#f44336',
}

const NO_RISK_COLOUR = '#cccccc'

export interface PlanningAreaFeature {
  name: string
  riskLevel: RiskLevel
  score: number
}

interface Props {
  areas: PlanningAreaFeature[]
  onAreaClick?: (area: PlanningAreaFeature) => void
  selectedArea?: string
  pinCoords?: [number, number]
}

function FlyToArea({ pinCoords }: { pinCoords?: [number, number] }) {
  const map = useMap()
  useEffect(() => {
    if (!pinCoords) return
    map.flyTo(pinCoords, 13, { duration: 1 })
  }, [pinCoords, map])
  return null
}

export default function ChoroplethMap({ areas, onAreaClick, selectedArea, pinCoords }: Props) {
  const [geoData, setGeoData] = useState<GeoJsonObject | null>(null)
  const geoJsonRef = useRef<LeafletGeoJSON>(null)

  useEffect(() => {
    getPlanningAreaBoundaries().then(setGeoData).catch(console.error)
  }, [])

  // After the GeoJSON layer mounts/updates, bring the selected polygon to front
  useEffect(() => {
    if (!geoJsonRef.current || !selectedArea) return
    geoJsonRef.current.eachLayer((layer) => {
      const feature = (layer as any).feature as Feature | undefined
      if (feature?.properties?.name?.toUpperCase() === selectedArea.toUpperCase()) {
        ;(layer as any).bringToFront()
      }
    })
  }, [selectedArea, geoData])

  // Build lookup: UPPERCASE name → area data
  const riskMap = new Map(areas.map((a) => [a.name.toUpperCase(), a]))

  const getStyle = (feature?: Feature) => {
    const name = (feature?.properties?.name as string | undefined)?.toUpperCase() ?? ''
    const area = riskMap.get(name)
    const isSelected = !!selectedArea && selectedArea.toUpperCase() === name
    return {
      fillColor: area ? RISK_COLOURS[area.riskLevel] : NO_RISK_COLOUR,
      fillOpacity: isSelected ? 0.9 : 0.6,
      color: '#ffffff',
      weight: isSelected ? 3 : 1,
    }
  }

  const onEachFeature = (feature: Feature, layer: Layer) => {
    const name = (feature.properties?.name as string) ?? ''
    const area = riskMap.get(name.toUpperCase())
    const popup = area
      ? `<div style="min-width:140px;font-family:sans-serif">
           <div style="font-size:14px;font-weight:700;margin-bottom:6px">${area.name}</div>
           <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;color:#fff;background:${RISK_COLOURS[area.riskLevel]}">${area.riskLevel} Risk</span>
         </div>`
      : `<div style="font-family:sans-serif;font-size:13px"><strong>${name}</strong><br/><span style="color:#888">No data</span></div>`
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(layer as any).bindPopup(popup)
    if (area) {
      layer.on('click', () => onAreaClick?.(area))
    }
  }

  // Key forces GeoJSON layer to re-render when risk data or selection changes
  const geoKey = areas.map((a) => `${a.name}:${a.riskLevel}`).join(',') + (selectedArea ?? '')

  const selectedAreaData = selectedArea
    ? areas.find((a) => a.name.toUpperCase() === selectedArea.toUpperCase())
    : null

  // Marker position: use pinCoords from postal code lookup (exact OneMap coordinates)
  const markerPos: [number, number] | null = pinCoords ?? null

  return (
    <div className={styles.mapWrapper}>
      <MapContainer
        center={[1.3521, 103.8198]}
        zoom={11}
        className={styles.leafletMap}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FlyToArea pinCoords={pinCoords} />
        {geoData && (
          <GeoJSON
            key={geoKey}
            ref={geoJsonRef}
            data={geoData}
            style={getStyle}
            onEachFeature={onEachFeature}
          />
        )}
        {markerPos && (
          <Marker position={markerPos} icon={pinIcon}>
            <Popup>
              <div style={{ minWidth: 140, fontFamily: 'sans-serif' }}>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>
                  {selectedAreaData?.name ?? selectedArea}
                </div>
                {selectedAreaData && (
                  <span style={{
                    display: 'inline-block',
                    padding: '3px 10px',
                    borderRadius: 12,
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#fff',
                    background: RISK_COLOURS[selectedAreaData.riskLevel],
                  }}>
                    {selectedAreaData.riskLevel} Risk
                  </span>
                )}
              </div>
            </Popup>
          </Marker>
        )}
      </MapContainer>

      <ul className={styles.legend}>
        {(Object.entries(RISK_COLOURS) as [RiskLevel, string][]).map(([level, colour]) => (
          <li key={level} className={styles.legendItem}>
            <span className={styles.legendDot} style={{ backgroundColor: colour }} />
            {level} Risk
          </li>
        ))}
      </ul>
    </div>
  )
}
