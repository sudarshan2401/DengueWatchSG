import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { unsubscribe } from '../api'
import logo from '../assets/logo.png'
import styles from './UnsubscribePage.module.css'

type Status = 'loading' | 'success' | 'error'

export default function UnsubscribePage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<Status>('loading')
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const uuid = searchParams.get('uuid')
    if (!uuid) {
      setStatus('error')
      setErrorMessage('No subscription ID was provided. The link in your email may be invalid.')
      return
    }

    unsubscribe(uuid)
      .then(() => setStatus('success'))
      .catch((err) => {
        setStatus('error')
        const statusCode = err?.response?.status
        if (statusCode === 404) {
          setErrorMessage('Subscription not found. It may have already been removed.')
        } else {
          setErrorMessage('Something went wrong. Please try again later.')
        }
      })
  }, [searchParams])

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
        {status === 'loading' && (
          <div className={styles.card}>
            <div className={styles.spinner} />
            <p className={styles.loadingText}>Processing your request…</p>
          </div>
        )}

        {status === 'success' && (
          <div className={styles.card}>
            <div className={styles.iconSuccess}>✓</div>
            <h2 className={styles.heading}>Successfully Unsubscribed</h2>
            <p className={styles.message}>
              You have successfully unsubscribed from this Dengue Watch SG alert.
            </p>
            <button className={styles.btnPrimary} onClick={() => navigate('/')}>
              Back to Map
            </button>
          </div>
        )}

        {status === 'error' && (
          <div className={styles.card}>
            <div className={styles.iconError}>✕</div>
            <h2 className={styles.headingError}>Unsubscribe Failed</h2>
            <p className={styles.message}>{errorMessage}</p>
            <button className={styles.btnPrimary} onClick={() => navigate('/')}>
              Back to Map
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
