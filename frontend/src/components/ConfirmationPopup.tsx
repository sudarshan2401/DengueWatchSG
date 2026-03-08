import styles from './ConfirmationPopup.module.css'

interface ConfirmationPopupProps {
  message: string
  onClose: () => void
}

export default function ConfirmationPopup({ message, onClose }: ConfirmationPopupProps) {
  return (
    <div className={styles['popup-overlay']}>
      <div className={styles['popup-content']}>
        <h2>Subscription Confirmed!</h2>
        <p>{message}</p>
        <button className={styles['popup-button']} onClick={onClose}>
          Got it!
        </button>
      </div>
    </div>
  )
}
