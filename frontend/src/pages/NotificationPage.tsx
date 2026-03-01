import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { subscribe } from '../api'
import styles from './NotificationPage.module.css'

export default function NotificationPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [postalInput, setPostalInput] = useState('')
  const [postalCodes, setPostalCodes] = useState<string[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')

  function addPostalCode() {
    const code = postalInput.trim()
    if (!/^\d{6}$/.test(code)) {
      setMessage('Please enter a valid 6-digit postal code.')
      return
    }
    if (postalCodes.includes(code)) {
      setMessage('Postal code already added.')
      return
    }
    setPostalCodes((prev) => [...prev, code])
    setPostalInput('')
    setMessage('')
  }

  function removePostalCode(code: string) {
    setPostalCodes((prev) => prev.filter((c) => c !== code))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email) {
      setMessage('Please enter your email address.')
      return
    }
    if (postalCodes.length === 0) {
      setMessage('Please add at least one postal code to monitor.')
      return
    }
    setStatus('loading')
    setMessage('')
    try {
      await subscribe({ email, postalCodes })
      setStatus('success')
      setMessage(`You're subscribed! We'll notify ${email} when risk levels change.`)
    } catch {
      setStatus('error')
      setMessage('Subscription failed. Please try again.')
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/')}>
          ← Back to Map
        </button>
        <div className={styles.headerCenter}>
          <span>🦟</span>
          <h1>DengueWatch SG</h1>
        </div>
        <span />
      </header>

      <main className={styles.main}>
        <h2 className={styles.heading}>🔔 Subscribe to Risk Alerts</h2>
        <p className={styles.subheading}>
          Receive email notifications when dengue risk worsens in your monitored areas.
        </p>

        {status === 'success' ? (
          <div className={styles.success}>
            <p>✅ {message}</p>
            <button className={styles.btnPrimary} onClick={() => navigate('/')}>
              Back to Map
            </button>
          </div>
        ) : (
          <form className={styles.form} onSubmit={handleSubmit}>
            {/* Email input */}
            <label className={styles.label} htmlFor="email">
              Email Address
            </label>
            <input
              id="email"
              className={styles.input}
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            {/* Postal code input */}
            <label className={styles.label} htmlFor="postal">
              Postal Codes to Monitor
            </label>
            <div className={styles.postalRow}>
              <input
                id="postal"
                className={styles.input}
                type="text"
                placeholder="6-digit postal code"
                value={postalInput}
                onChange={(e) => setPostalInput(e.target.value)}
                maxLength={6}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addPostalCode())}
              />
              <button
                type="button"
                className={styles.btnSecondary}
                onClick={addPostalCode}
              >
                Add
              </button>
            </div>

            {/* Added postal codes */}
            {postalCodes.length > 0 && (
              <ul className={styles.codeList}>
                {postalCodes.map((code) => (
                  <li key={code} className={styles.codeChip}>
                    {code}
                    <button
                      type="button"
                      className={styles.removeBtn}
                      onClick={() => removePostalCode(code)}
                      aria-label={`Remove ${code}`}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {message && (
              <p className={status === 'error' ? styles.errorMsg : styles.infoMsg}>
                {message}
              </p>
            )}

            <button
              type="submit"
              className={styles.btnPrimary}
              disabled={status === 'loading'}
            >
              {status === 'loading' ? 'Subscribing…' : 'Subscribe'}
            </button>
          </form>
        )}
      </main>
    </div>
  )
}
