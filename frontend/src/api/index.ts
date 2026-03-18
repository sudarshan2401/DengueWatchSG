import axios from 'axios'
import type { GeoJsonObject } from 'geojson'
import type { PlanningAreaRisk, PostalCodeInfo, Subscription } from '../types'

const BASE_URL = 'https://vod0qxda75.execute-api.ap-southeast-1.amazonaws.com/default/dengue-api'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? BASE_URL,
})

interface RiskApiResponse {
  week: string
  data: {
    planning_area: string
    risk_level: string
    score: number
    latitude: number
    longitude: number
  }[]
}

/** Fetch current risk scores for all planning areas */
export async function getRiskMap(): Promise<PlanningAreaRisk[]> {
  const { data } = await api.get<RiskApiResponse>('/risk')
  return data.data.map((r) => ({
    planningArea: r.planning_area,
    riskLevel: r.risk_level as PlanningAreaRisk['riskLevel'],
    score: r.score,
    week: data.week,
    latitude: r.latitude,
    longitude: r.longitude,
  }))
}

/** Look up planning area and risk level for a postal code */
export async function lookupPostalCode(postalCode: string): Promise<PostalCodeInfo> {
  const { data } = await api.get<PostalCodeInfo>(`/postal-code/${postalCode}`)
  return data
}

/** Subscribe an email address to monitor given planning areas */
export async function subscribe(payload: Subscription): Promise<void> {
  await api.post('/subscribe', payload)
}

/** Fetch Singapore planning area boundary GeoJSON from OneMap via backend */
export async function getPlanningAreaBoundaries(): Promise<GeoJsonObject> {
  const { data } = await api.get<GeoJsonObject>('/planning-areas')
  return data
}
