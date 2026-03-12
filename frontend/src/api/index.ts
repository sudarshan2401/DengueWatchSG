import axios from 'axios'
import type { PlanningAreaRisk, PostalCodeInfo, Subscription } from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
})

/** Fetch current risk scores for all planning areas */
export async function getRiskMap(): Promise<PlanningAreaRisk[]> {
  const { data } = await api.get<PlanningAreaRisk[]>('/risk-map')
  return data
}

/** Look up planning area and risk level for a postal code */
export async function lookupPostalCode(postalCode: string): Promise<PostalCodeInfo> {
  const { data } = await api.get<PostalCodeInfo>(`/postal-code/${postalCode}`)
  return data
}

/** Subscribe an email address to monitor given planning areas */
export async function subscribe(payload: Subscription): Promise<void> {
  await api.post('/subscriptions', payload)
}
