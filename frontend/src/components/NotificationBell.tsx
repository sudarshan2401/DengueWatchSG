import { useNavigate } from 'react-router-dom'
import styles from './NotificationBell.module.css'

interface Props {
  /** Number of unread notifications (not yet implemented) */
  count?: number
}

export default function NotificationBell({ count = 0 }: Props) {
  const navigate = useNavigate()

  return (
    <button
      className={styles.bell}
      aria-label={`Notifications${count > 0 ? ` (${count} unread)` : ''}`}
      onClick={() => navigate('/subscribe')}
    >
      🔔
      {count > 0 && <span className={styles.badge}>{count}</span>}
    </button>
  )
}
