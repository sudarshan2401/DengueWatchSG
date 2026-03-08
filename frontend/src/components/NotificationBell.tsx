import { useNavigate } from 'react-router-dom'
import { FiBell } from 'react-icons/fi'
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
      <FiBell />
      {count > 0 && <span className={styles.badge}>{count}</span>}
    </button>
  )
}
