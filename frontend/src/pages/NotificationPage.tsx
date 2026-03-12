import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { subscribe, lookupPostalCode } from '../api'
import ConfirmationPopup from '../components/ConfirmationPopup'
import logo from '../assets/logo.png'
import styles from './NotificationPage.module.css'

export default function NotificationPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [postalInput, setPostalInput] = useState('')
  const [postalCodes, setPostalCodes] = useState<string[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [emailError, setEmailError] = useState('')
  const [postalError, setPostalError] = useState('')
  const [showPopup, setShowPopup] = useState(false)

  function handleEmailChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value
    setEmail(value)
    if (value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      setEmailError('Please enter a valid email address.')
    } else {
      setEmailError('')
    }
  }

  function handlePostalInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value
    setPostalInput(value)
    if (value && !/^(0[1-9]|[1-7][0-9]|8[0-2])\d{4}$/.test(value)) {
      setPostalError('Please enter a valid Singapore postal code.')
    } else {
      setPostalError('')
    }
  }

  function addPostalCode() {
    const code = postalInput.trim()
    if (!/^(0[1-9]|[1-7][0-9]|8[0-2])\d{4}$/.test(code)) {
      setPostalError('Please enter a valid Singapore postal code.')
      return
    }
    if (postalCodes.includes(code)) {
      setPostalError('Postal code already added.')
      return
    }
    setPostalCodes((prev) => [...prev, code])
    setPostalInput('')
    setPostalError('')
    setMessage('')
  }

  function removePostalCode(code: string) {
    setPostalCodes((prev) => prev.filter((c) => c !== code))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setMessage('Please enter a valid email address.')
      return
    }
    if (postalCodes.length === 0) {
      setMessage('Please add at least one postal code to monitor.')
      return
    }

    setStatus('loading')
    setMessage('Resolving postal codes…')

    let planning_areas: string[]
    try {
      const results = await Promise.all(postalCodes.map((code) => lookupPostalCode(code)))
      planning_areas = [...new Set(results.map((r) => r.planningArea))]
    } catch {
      setStatus('error')
      setMessage('Could not resolve one or more postal codes. Please check them and try again.')
      return
    }

    try {
      await subscribe({ email, planning_areas })
      setStatus('success')
      setMessage(`You're subscribed! We'll notify ${email} when risk levels change.`)
      setShowPopup(true)
    } catch {
      setStatus('error')
      setMessage('Subscription failed. Please try again later.')
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/')}>
          ← Map
        </button>
        <div className={styles.headerCenter}>
          <img src={logo} alt="DengueWatch SG" className={styles.logoImage} />
          <h1>DengueWatch SG</h1>
        </div>
        <span />
      </header>

      <main className={styles.main}>
        <h2 className={styles.heading}>Subscribe to Risk Alerts</h2>
        <p className={styles.subheading}>
          Receive email notifications when dengue risk worsens in your monitored areas.
        </p>

        {status === 'success' && showPopup ? (
          <ConfirmationPopup
            message={message}
            onClose={() => {
              setShowPopup(false)
              navigate('/')
            }}
          />
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
              onChange={handleEmailChange}
              required
            />
            {emailError && <p className={styles.errorMsg}>{emailError}</p>}

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
                onChange={handlePostalInputChange}
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
            {postalError && <p className={styles.errorMsg}>{postalError}</p>}

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
              disabled={status === 'loading' || !!emailError || !!postalError || status === 'success'}
            >
              {status === 'loading' ? 'Subscribing…' : 'Subscribe'}
            </button>
          </form>
        )}
      </main>
    </div>
  )
}
