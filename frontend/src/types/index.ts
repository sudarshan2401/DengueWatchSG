/** Dengue risk level for a Singapore planning area */
export type RiskLevel = 'Low' | 'Medium' | 'High'

export interface PlanningAreaRisk {
  planningArea: string
  riskLevel: RiskLevel
  /** Predicted probability score 0–1 */
  score: number
  /** ISO week string, e.g. "2024-W10" */
  week: string
  latitude: number
  longitude: number
}

export interface PostalCodeInfo {
  postalCode: string
  planningArea: string
  riskLevel: RiskLevel
  latitude: number
  longitude: number
}

export interface Subscription {
  email: string
  planning_areas: string[]
}
