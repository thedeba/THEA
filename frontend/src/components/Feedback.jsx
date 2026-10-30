export function Spinner({ label = "Loading" }) {
  return (
    <div className="spinner-row" role="status">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  );
}

export function PageLoader({ label = "Loading" }) {
  return (
    <div className="page-loader">
      <Spinner label={label} />
    </div>
  );
}

export function ErrorBanner({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className="error-banner" role="alert">
      <span>{message}</span>
      {onRetry ? (
        <button type="button" className="ghost-button small" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, message, action }) {
  return (
    <div className="empty-state">
      <div className="empty-mark" />
      <h3>{title}</h3>
      {message ? <p>{message}</p> : null}
      {action}
    </div>
  );
}
