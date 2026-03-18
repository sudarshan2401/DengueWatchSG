import { useState, type FormEvent } from 'react'
import { lookupPostalCode } from '../api'
import type { PostalCodeInfo, RiskLevel } from '../types'
import { RISK_COLOURS } from './ChoroplethMap'
import styles from './PostalCodeSearch.module.css'

interface Props {
  onResult?: (info: PostalCodeInfo) => void
  riskByArea?: Map<string, RiskLevel>
}

export default function PostalCodeSearch({ onResult, riskByArea }: Props) {
  const [value, setValue] = useState('')
  const [result, setResult] = useState<PostalCodeInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const code = e.target.value
    setValue(code)
    if (code && !/^(0[1-9]|[1-7][0-9]|8[0-2])\d{4}$/.test(code)) {
      setError('Please enter a valid Singapore postal code.')
    } else {
      setError(null)
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const code = value.trim()
    if (!/^(0[1-9]|[1-7][0-9]|8[0-2])\d{4}$/.test(code)) {
      setError('Please enter a valid Singapore postal code.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const raw = await lookupPostalCode(code)
      const riskLevel = riskByArea?.get(raw.planningArea) as PostalCodeInfo['riskLevel']
      const info: PostalCodeInfo = { ...raw, riskLevel }
      setResult(info)
      onResult?.(info)
    } catch {
      setError('Postal code not found. Please try again.')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.wrapper}>
      <form className={styles.form} onSubmit={handleSubmit}>
        <input
          className={styles.input}
          type="text"
          placeholder="Enter postal code (e.g. 238801)"
          value={value}
          onChange={handleChange}
          maxLength={6}
          aria-label="Postal code"
        />
        <button className={styles.button} type="submit" disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && <p className={styles.error}>{error}</p>}

      {result && (
        <div
          className={styles.result}
          style={{ borderLeft: `4px solid ${RISK_COLOURS[result.riskLevel]}` }}
        >
          <span className={styles.area}>
            <span className={styles.postalCode}>{result.postalCode}</span>
            <span className={styles.areaDivider}>—</span>
            <span className={styles.areaName}>{result.planningArea}</span>
          </span>
          <span
            className={styles.badge}
            style={{ backgroundColor: RISK_COLOURS[result.riskLevel] }}
          >
            {result.riskLevel} Risk
          </span>
        </div>
      )}
    </div>
  )
}
