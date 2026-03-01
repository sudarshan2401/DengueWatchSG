import { useState, type FormEvent } from 'react'
import { lookupPostalCode } from '../api'
import type { PostalCodeInfo } from '../types'
import { RISK_COLOURS } from './ChoroplethMap'
import styles from './PostalCodeSearch.module.css'

interface Props {
  onResult?: (info: PostalCodeInfo) => void
}

export default function PostalCodeSearch({ onResult }: Props) {
  const [value, setValue] = useState('')
  const [result, setResult] = useState<PostalCodeInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const code = value.trim()
    if (!/^\d{6}$/.test(code)) {
      setError('Please enter a valid 6-digit Singapore postal code.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const info = await lookupPostalCode(code)
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
          onChange={(e) => setValue(e.target.value)}
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
          <span className={styles.area}>{result.planningArea}</span>
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
